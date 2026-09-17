"""Synthetic lifecycle and original-delivery checks; no university credentials."""
import asyncio
import base64
import hashlib
import io
import json
import time
import zipfile

import pytest
from edinburgh_study_agent import nmr, nmr_auth, delivery, contracts
from edinburgh_study_agent.nmr_client import NmrError
from edinburgh_study_agent.store import Store


def raw_zip(prefix="Synthetic-0042/10/"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(prefix+"fid", b"synthetic raw bytes\x00\x01")
        archive.writestr(prefix+"acqus", b"##TITLE= synthetic acquisition\n")
    return stream.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = Store(tmp_path)
    session = {"provider": "nomad", "user_id": "a"*24, "username": "synthetic", "token": "private", "expires_at": time.time()+300}
    state = {"session": session, "download_calls": 0, "search_calls": 0, "body": raw_zip(), "datasets": ["Synthetic-0042"]}
    monkeypatch.setattr(nmr_auth, "get_session", lambda *a: state["session"])

    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def search(self, sample, **kwargs):
            state["search_calls"] += 1
            return {"datasets": [{"dataset_name": d, "title": "0042", "user": "synthetic", "group": "teaching", "instrument": "test"} for d in state["datasets"]], "has_more": False}
        def experiments(self, dataset):
            return [{"dataset_name": dataset, "experiment_number": "10", "experiment_id": dataset+"-10", "title": "0042"}]
        def download(self, ident, path, size, **kwargs):
            state["download_calls"] += 1
            if state.get("error"): raise NmrError(state["error"], "Sanitized error")
            with path.open("xb") as stream: stream.write(state["body"])
            if state.get("cancel_after_transfer"): kwargs["cancel_event"].set()
            return len(state["body"])
    monkeypatch.setattr(nmr, "NomadClient", Client)
    yield store, state
    for panel in list(nmr_auth._PANELS.values()):
        if panel.root == tmp_path:
            panel.stop.set()
            panel.thread.join(2)


def validate(value):
    stamped = {**value, "_contract": {"version": "1", "operation": "study_nmr"}}
    contracts.validate_result("study_nmr", stamped)
    return value


def test_missing_information_resumes_without_losing_zeroes(env):
    store, state = env
    state["session"] = None
    first = validate(nmr.run(store, "find", sample="0042"))
    assert first["state"] == "needs_input" and first["needed"] == ["provider"]
    state["session"] = None
    second = validate(nmr.run(store, "resume", provider="nomad", request_id=first["request_id"]))
    assert second["state"] == "authentication_pending" and second["sample"] == "0042"
    assert second["request_id"] == first["request_id"] and state["search_calls"] == 0


def test_verified_download_then_cache_and_export_receipt(env):
    store, state = env
    found = validate(nmr.run(store, "find", provider="nomad", sample="0042"))
    done = validate(nmr.run(store, "download", request_id=found["request_id"]))
    assert done["state"] == "downloaded" and not done["cache_hit"]
    assert done["integrity"]["raw_files"] == ["fid"]
    cached = validate(nmr.run(store, "download", request_id=found["request_id"]))
    assert cached["cache_hit"] and state["download_calls"] == 1 and state["search_calls"] == 1
    exported = delivery.export_files(store, [done["files"][0]["item_id"]])
    assert exported.structuredContent["state"] == "awaiting_host_receipt"
    body = base64.b64decode(exported.content[1].resource.blob)
    assert body == state["body"] and hashlib.sha256(body).hexdigest() == done["files"][0]["sha256"]
    assert b"private" not in store.db_path.read_bytes()


def test_multiple_dataset_selection_is_resumable_without_repeat_search(env):
    store, state = env
    state["datasets"] = ["Synthetic-0042", "Other-0042"]
    found = validate(nmr.run(store, "find", provider="nomad", sample="0042"))
    assert found["state"] == "needs_selection"
    chosen = validate(nmr.run(store, "resume", request_id=found["request_id"], selection_id="Synthetic-0042"))
    assert chosen["state"] == "ready" and state["search_calls"] == 1


@pytest.mark.parametrize("body,code", [(b"<html>sign in</html>", "NMR_ARCHIVE_INVALID_ZIP"),
                                      (raw_zip("Other/10/"), "NMR_ARCHIVE_EXPERIMENT_MISMATCH")])
def test_invalid_raw_download_never_records_or_exports(env, body, code):
    store, state = env
    state["body"] = body
    value = validate(nmr.run(store, "download", provider="nomad", sample="0042"))
    assert value["state"] == "unavailable" and value["code"] == code
    with store.connection() as db: assert db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0] == 0
    assert not list(store.root.rglob(".partial-*"))


def test_rejected_selected_download_asks_auth_and_retains_selection(env):
    store, state = env
    found = nmr.run(store, "find", provider="nomad", sample="0042")
    state["error"] = "AUTH_REQUIRED"
    value = validate(nmr.run(store, "download", request_id=found["request_id"], selection_id=found["results"][0]["id"]))
    assert value["state"] == "needs_auth" and value["request_id"] == found["request_id"]
    assert state["download_calls"] == 1 and not list(store.root.rglob(".partial-*"))


def test_selection_and_account_scope_are_enforced(env):
    store, state = env
    found = nmr.run(store, "find", provider="nomad", sample="0042")
    with pytest.raises(ValueError, match="returned"):
        nmr.run(store, "download", request_id=found["request_id"], selection_id="invented")
    state["session"]["user_id"] = "b"*24
    value = validate(nmr.run(store, "download", request_id=found["request_id"]))
    assert value["state"] == "unavailable" and value["code"] == "SCOPE_MISMATCH"
    assert state["download_calls"] == 0


def test_http_consent_scope_and_no_password_arguments(env):
    store, state = env
    value = validate(nmr.run(store, "find", provider="legacy", sample="0042", group="3OR"))
    assert value["needed"] == ["insecure_http_consent"] and state["search_calls"] == 0
    from edinburgh_study_agent import server
    entry = next(x for x in asyncio.run(server.mcp.list_tools()) if x.name == "study_nmr")
    assert not ({"ctx", "password", "token"} & entry.inputSchema["properties"].keys())


def test_legacy_parent_prefix_is_bound(tmp_path):
    from edinburgh_study_agent.nmr_archive import inspect_archive
    path = tmp_path / "data.zip"
    path.write_bytes(raw_zip("3OR/SyntheticUser/Synthetic-0042/10/"))
    assert inspect_archive(path, "Synthetic-0042", "10", parent_components=("3OR", "SyntheticUser"))["file_count"] == 2
    with pytest.raises(ValueError, match="EXPERIMENT_MISMATCH"):
        inspect_archive(path, "Synthetic-0042", "10", parent_components=("2OR", "SyntheticUser"))


def test_protocol_status_and_missing_input_are_validated(env, monkeypatch):
    from edinburgh_study_agent import server
    store, _ = env
    monkeypatch.setattr(server, "store", lambda: store)
    for args in ({}, {"action": "find", "sample": "0042"}):
        result = asyncio.run(server.mcp.call_tool("study_nmr", args))
        assert not result.isError, result.structuredContent
        assert json.loads(result.content[0].text) == result.structuredContent
        contracts.validate_result("study_nmr", result.structuredContent)


def test_download_schema_rejects_false_completion():
    with pytest.raises(contracts.OutputValidationError):
        validate({"state": "downloaded", "provider": "nomad", "message": "invented"})


def test_cancellation_before_promotion_leaves_no_successful_download(env):
    import threading
    store, state = env
    state["cancel_after_transfer"] = True
    value = validate(nmr.run(store, "download", provider="nomad", sample="0042", cancel_event=threading.Event()))
    assert value["code"] == "CANCELLED" and value["state"] == "unavailable"
    assert not list(store.root.rglob(".partial-*"))
    with store.connection() as db: assert db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0] == 0


def test_mcp_cancellation_reaches_the_sync_worker(env, monkeypatch):
    import threading
    from edinburgh_study_agent import server
    started, observed = threading.Event(), threading.Event()
    def waiting(*args, cancel_event, **kwargs):
        started.set()
        assert cancel_event.wait(2)
        observed.set()
        return {}
    monkeypatch.setattr(nmr, "run", waiting)
    monkeypatch.setattr(server, "store", lambda: env[0])
    async def scenario():
        task = asyncio.create_task(server.study_nmr())
        while not started.is_set(): await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert await asyncio.to_thread(observed.wait, 2)
    asyncio.run(scenario())


def test_legacy_layout_change_is_not_empty_results():
    from edinburgh_study_agent.nmr_legacy import parse_results
    page = 'Search Results Searched <table><tr><td><a href="/archive/3OR/SyntheticUser/data.zip">0042</a></td></tr></table>'
    with pytest.raises(NmrError) as error:
        parse_results(page, "0042", "3OR")
    assert error.value.code == "UNSUPPORTED_LAYOUT"


def test_missing_nmr_cache_recovers_via_nmr_tool(env):
    store, _ = env
    found = nmr.run(store, "find", provider="nomad", sample="0042")
    with pytest.raises(ValueError, match="study_nmr download"):
        delivery.export_files(store, [found["results"][0]["id"]])


def test_resume_download_keeps_original_intent_after_sample_question(env):
    store, state = env
    missing = validate(nmr.run(store, "download", provider="nomad"))
    assert missing["needed"] == ["sample"]
    done = validate(nmr.run(store, "resume", request_id=missing["request_id"], sample="0042"))
    assert done["state"] == "downloaded" and state["download_calls"] == 1


def test_resume_download_accepts_observed_dataset_selection(env):
    store, state = env
    state["datasets"] = ["Synthetic-0042", "Other-0042"]
    choices = validate(nmr.run(store, "download", provider="nomad", sample="0042"))
    assert choices["state"] == "needs_selection"
    done = validate(nmr.run(store, "resume", request_id=choices["request_id"], selection_id="Synthetic-0042"))
    assert done["state"] == "downloaded" and state["search_calls"] == 1
