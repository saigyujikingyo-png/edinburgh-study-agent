"""Measure isolated MCP catalogs and cached status calls; no model or campus data."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
from time import perf_counter

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from edinburgh_study_agent import __version__


async def measure(profile, iterations):
    with tempfile.TemporaryDirectory(prefix="uoe-contract-benchmark-") as data:
        environment = dict(os.environ, EDINBURGH_STUDY_HOME=data, UOE_TOOL_PROFILE=profile,
                           UOE_LOCALE="auto", PYTHONUTF8="1")
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).with_name("run_server.py"))], env=environment)
        started = perf_counter()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                initialized_ms = (perf_counter() - started) * 1000
                started = perf_counter()
                catalog = await session.list_tools()
                discovery_ms = (perf_counter() - started) * 1000
                timings = []
                result_bytes = []
                for _ in range(iterations + 1):
                    started = perf_counter()
                    result = await session.call_tool("study_status", {})
                    timings.append((perf_counter() - started) * 1000)
                    assert not result.isError
                    assert result.structuredContent["live_connection_checked"] is False
                    assert result.structuredContent["_contract"] == {"version": "1", "operation": "study_status"}
                    assert json.loads(result.content[0].text) == result.structuredContent
                    result_bytes.append(len(result.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")))
                advanced = None
                if profile == "daily":
                    description = await session.call_tool("study_more", {"mode": "describe", "tool": "study_tasks"})
                    assert not description.isError and description.structuredContent["outputSchema"]
                    called = await session.call_tool("study_more", {"mode": "call", "tool": "study_tasks"})
                    assert not called.isError and called.structuredContent["_contract"]["operation"] == "study_tasks"
                    assert json.loads(called.content[0].text) == called.structuredContent
                    advanced = {"described": "study_tasks", "validated_call": True}
                return {"profile": profile, "tools": len(catalog.tools),
                    "output_schemas": sum(bool(tool.outputSchema) for tool in catalog.tools),
                    "catalog_utf8_bytes": len(catalog.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")),
                    "initialize_ms": round(initialized_ms, 2), "discovery_ms": round(discovery_ms, 2),
                    "first_status_ms": round(timings[0], 2), "warm_status_median_ms": round(statistics.median(timings[1:]), 2),
                    "warm_status_max_ms": round(max(timings[1:]), 2), "warm_calls": iterations,
                    "status_result_utf8_bytes": result_bytes[-1], "advanced_check": advanced}


async def run(iterations):
    return {"version": __version__, "contract_version": "1", "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.system(), "transport": "stdio",
        "data": "isolated empty synthetic stores", "model": None, "actual_tokens": None,
        "billing_or_quota_usage": None, "automatic_retries": 0,
        "measurement_note": "Serialized UTF-8 sizes and local protocol elapsed times; not model tokens, network traffic or billing.",
        "profiles": [await measure(profile, iterations) for profile in ("full", "student", "daily")]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    if not 2 <= args.iterations <= 100:
        parser.error("iterations must be between 2 and 100")
    print(json.dumps(asyncio.run(run(args.iterations)), indent=2))
