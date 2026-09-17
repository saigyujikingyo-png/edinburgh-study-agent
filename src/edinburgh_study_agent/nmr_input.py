"""Thin MCP input adapter: ordinary fields in-host; credentials out of band."""
from __future__ import annotations

import asyncio
import threading
from typing import Literal

from pydantic import Field, create_model

from . import nmr


def input_model(needed):
    """The allowlist cannot ever contain passwords, tokens or credential fields."""
    fields = {
        "sample": (str, Field(min_length=1, max_length=128, title="NMR sample number (keep leading zeros)")),
        "provider": (Literal["nomad", "legacy"], Field(title="NMR source")),
        "group": (Literal["3OR", "2OR"], Field(title="Teaching archive group")),
    }
    if not needed or set(needed) - fields.keys():
        return None
    return create_model("NmrQueryInput", **{key: fields[key] for key in needed})


async def _run(store, action, **kwargs):
    cancellation = threading.Event()
    worker = asyncio.create_task(asyncio.to_thread(nmr.run, store, action, **kwargs, cancel_event=cancellation))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancellation.set()
        worker.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        raise


async def interact(store, action, *, ctx=None, **kwargs):
    value = await _run(store, action, **kwargs)
    if ctx is None or value["state"] not in ("needs_input", "authentication_pending"):
        return value
    try:
        capabilities = getattr(getattr(ctx.session, "client_params", None), "capabilities", None)
    except (ValueError, AttributeError):
        return value  # In-process tool calls may not have a live MCP request.
    elicitation = getattr(capabilities, "elicitation", None)
    if value["state"] == "needs_input" and elicitation is not None and getattr(elicitation, "form", None) is not None:
        model = input_model(value.get("needed", []))
        if model is not None:
            try:
                answer = await ctx.elicit(message="Complete the missing NMR sample details. No password is requested here.", schema=model)
            except Exception:
                return value  # The same bounded question remains available in chat.
            if answer.action == "accept" and answer.data is not None:
                resumed = {**kwargs, **answer.data.model_dump(), "request_id": value["request_id"]}
                value = await _run(store, "resume", **resumed)
    if value["state"] == "authentication_pending" and elicitation is not None and getattr(elicitation, "url", None) is not None:
        try:
            await ctx.elicit_url(message=value["message"], url=value["connection"]["url"],
                                 elicitation_id=value["connection"]["connection_id"])
        except Exception:
            pass  # Link fallback; never ask for secrets via form-mode elicitation.
    return value
