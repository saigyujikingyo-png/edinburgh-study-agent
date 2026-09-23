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
            state["last_search"] = {"sample": sample, **kwargs}
            return {"datasets": [{"dataset_name": d, "title": "0042", "user": "synthetic", "group": "teaching", "instrument": "test"} for d in state["datasets"]], "has_more": False, "total_datasets": len(state["datasets"]), "coverage": "bounded_personal_archive" if sample is None else "bounded_authenticated_sample_search", "order": "last_archived_desc"}
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


def test_new_nmr_receipt_satisfies_shared_download_contract(env):
    from edinburgh_study_agent.downloads import list_downloads
    store, state = env
    done = validate(nmr.run(store,"download",provider="nomad",sample="0042"))
    assert done["state"] == "downloaded"
    records = list_downloads(store)
    assert records["files"][0]["title"] == records["files"][0]["filename"]
    assert records["files"][0]["title_source"] == "filename"
    contracts.validate_result("study_downloads",
        {**records,"_contract":{"version":"1","operation":"study_downloads"}})
    with store.connection() as db:
        stored = json.loads(db.execute("SELECT payload FROM downloads").fetchone()[0])
    assert stored["title"] == stored["filename"] and state["download_calls"] == 1


def test_nomad_list_does_not_need_sample_or_download(env):
    store, state = env
    result = validate(nmr.run(store, "list", start_date="2026-09-01", end_date="2026-09-01", limit=5))
    assert result["provider"] == "nomad" and result["state"] == "needs_selection"
    assert result["sample"] is None and result["total_datasets"] == 1
    assert result["source_transport"] == "https" and result["order"] == "last_archived_desc"
    assert state["download_calls"] == 0 and state["search_calls"] == 1
    assert state["last_search"]["sample"] is None
    assert result["coverage"] == "bounded_personal_archive"


def test_list_then_selected_download_does_not_repeat_archive_search(env):
    store, state = env
    result = validate(nmr.run(store, "list"))
    downloaded = validate(nmr.run(store, "download", request_id=result["request_id"],
                                  selection_id=result["datasets"][0]["dataset_name"]))
    assert downloaded["state"] == "downloaded"
    assert state["search_calls"] == 1 and state["download_calls"] == 1
    cached = validate(nmr.run(store, "download", request_id=result["request_id"]))
    assert cached["cache_hit"] is True and state["download_calls"] == 1


def test_list_without_selection_never_guesses_or_downloads_unique_dataset(env):
    store, state = env
    first = validate(nmr.run(store, "list"))
    result = validate(nmr.run(store, "download", request_id=first["request_id"]))
    assert result["state"] == "needs_selection" and state["download_calls"] == 0


def test_list_retains_page_date_and_limit_across_authentication(env):
    store, state = env
    session = state["session"]
    state["session"] = None
    pending = validate(nmr.run(store, "list", page=3, limit=4, start_date="2026-09-01", end_date="2026-09-02"))
    assert pending["state"] == "authentication_pending" and state["search_calls"] == 0
    state["session"] = session
    result = validate(nmr.run(store, "resume", request_id=pending["request_id"]))
    assert result["state"] == "needs_selection" and result["page"] == 3 and result["limit"] == 4
    assert state["last_search"] == {"sample": None, "page": 3, "limit": 4,
                                    "start_date": "2026-09-01", "end_date": "2026-09-02"}


def test_list_empty_page_reports_scope_without_inventing_missing_sample(env):
    store, state = env
    state["datasets"] = []
    result = validate(nmr.run(store, "list"))
    assert result["state"] == "no_matches" and result["datasets"] == [] and result["total_datasets"] == 0
    assert "needed" not in result and state["download_calls"] == 0


def test_list_cannot_download_an_unobserved_or_stale_dataset(env):
    store, state = env
    result = validate(nmr.run(store, "list"))
    with pytest.raises(ValueError, match="returned for this NMR request"):
        nmr.run(store, "download", request_id=result["request_id"], selection_id="not-observed")
    with pytest.raises(ValueError, match="returned for this NMR request"):
        nmr.run(store, "download", request_id=result["request_id"], selection_id="Synthetic-0042",
                start_date="2026-09-02")
    assert state["download_calls"] == 0


def test_legacy_does_not_gain_broad_archive_listing(env):
    store, state = env
    with pytest.raises(ValueError, match="for NOMAD"):
        nmr.run(store, "list", provider="legacy", group="3OR")
    assert state["search_calls"] == 0


def test_network_failure_preserves_session_and_request_without_retry(env, monkeypatch):
    store, state = env
    from edinburgh_study_agent import nmr_network
    monkeypatch.setattr(nmr_network, "vpn_adapter", lambda: {"detected": True, "active": False})
    def fail(*args, **kwargs):
        state["search_calls"] += 1
        raise NmrError("NETWORK_UNAVAILABLE", "DO_NOT_ECHO_PRIVATE_ERROR")
    monkeypatch.setattr(nmr.NomadClient, "search", fail)
    result = validate(nmr.run(store, "list"))
    assert result["state"] == "unavailable" and result["code"] == "NETWORK_UNAVAILABLE"
    assert result["network"]["state"] == "vpn_disconnected"
    assert result["recovery_action"] == "connect_campus_vpn_then_resume"
    assert result["automatic_retry"] is False and result["request_id"]
    assert state["session"] is not None and state["search_calls"] == 1
    assert "DO_NOT_ECHO" not in json.dumps(result)


def test_successful_calls_do_not_launch_vpn_detection(env, monkeypatch):
    from edinburgh_study_agent import nmr_network
    monkeypatch.setattr(nmr_network, "vpn_adapter", lambda: pytest.fail("No happy-path VPN process"))
    store, state = env
    validate(nmr.run(store, "status"))
    validate(nmr.run(store, "list"))


def test_nomad_list_available_through_real_tool_contract(env, monkeypatch):
    from edinburgh_study_agent import server
    store, state = env
    monkeypatch.setattr(server, "store", lambda: store)
    result = asyncio.run(server.mcp.call_tool("study_nmr", {"action": "list", "limit": 3}))
    assert not result.isError
    value = result.structuredContent
    contracts.validate_result("study_nmr", value)
    assert value["state"] == "needs_selection" and value["limit"] == 3
