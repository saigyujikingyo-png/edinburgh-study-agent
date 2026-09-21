"""Synthetic acceptance of the public MCP output boundary, not host acceptance."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import uuid

import httpx
from jsonschema import Draft202012Validator
from mcp.types import CallToolResult
import pytest

from edinburgh_study_agent import contracts, downloads, school, timetable, workflow_cache
from edinburgh_study_agent.models import Item, Observation, now_utc
from edinburgh_study_agent.store import Store


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    """Keep every profile's tool manager and all persisted data test-local."""
    database = Store(tmp_path / "student")
    monkeypatch.setattr(school.subprocess, "Popen", lambda *a, **k: pytest.fail("A contract test started a school worker"))

    def load(profile="full"):
        monkeypatch.setenv("UOE_TOOL_PROFILE", profile)
        monkeypatch.setenv("EDINBURGH_STUDY_HOME", str(database.root))
        monkeypatch.setenv("UOE_LOCALE", "auto")
        name = "edinburgh_study_agent._output_test_" + uuid.uuid4().hex
        source = Path(__file__).parents[1] / "src/edinburgh_study_agent/server.py"
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, "store", lambda: database)
        return module

    return load, database


@pytest.mark.parametrize("profile", ["full", "student", "daily"])
def test_live_scope_choices_and_recovery_contracts_across_profiles(profiles, profile, monkeypatch):
    from edinburgh_study_agent.school_errors import diagnostic
    load, database = profiles
    module = load(profile)
    chosen = success(call(module,"study_materials",{"operation":"list","refresh":True}),"study_materials")
    assert chosen["browser_started"] is False
    assert chosen["result"]["needs_course_selection"] is True
    assert chosen["result"]["remote_freshness_checked"] is False
    stamp=now_utc().isoformat()
    failed={"job_id":"a"*32,"action":"messages","state":"failed","updated_at":stamp,
            "poll_after_seconds":0,"failure":diagnostic("NETWORK_TIMEOUT",host="idp.ed.ac.uk",stage="campus_sign_in")}
    monkeypatch.setattr(school,"start_job",lambda *a,**k:failed)
    value=success(call(module,"study_messages",{"refresh":True}),"study_messages")
    assert value["failure"]["target_host"]=="idp.ed.ac.uk"
    assert value["failure"]["recovery_action"]=="check_connection"
    broken={**failed,"failure":{**failed["failure"],"target_host":"private-secret.example"}}
    monkeypatch.setattr(school,"start_job",lambda *a,**k:broken)
    rejected=failure(call(module,"study_messages",{"refresh":True}),"study_messages","OUTPUT_VALIDATION_ERROR")
    assert "private-secret" not in json.dumps(rejected)


def call(module, name, arguments=None):
    return asyncio.run(module.mcp.call_tool(name, arguments or {}))


def success(reply, operation):
    assert isinstance(reply, CallToolResult)
    assert not reply.isError, reply.structuredContent
    body = reply.structuredContent
    assert isinstance(body, dict)
    assert body["_contract"] == {"version": "1", "operation": operation}
    texts = [block.text for block in reply.content if block.type == "text"]
    assert len(texts) == 1 and json.loads(texts[0]) == body
    Draft202012Validator(contracts.output_schema(operation)).validate(body)
    contracts.validate_result(operation, body)
    return body


def failure(reply, operation, code):
    assert reply.isError is True
    body = reply.structuredContent
    assert body["contract_version"] == "1"
    assert body["error"]["code"] == code
    assert body["error"]["operation"] == operation
    assert body["error"]["message"] and body["error"]["recovery"]
    assert json.loads(reply.content[0].text) == body
    Draft202012Validator(contracts.output_schema(operation)).validate(body)
    return body


def seed(database):
    records = [
        Item(native_id="contract-course", kind="course", title="Synthetic Algebra", excerpt="Synthetic Algebra", url="https://www.learn.ed.ac.uk/ultra/courses/_1_1/outline"),
        Item(native_id="contract-file", kind="resource", title="Synthetic notes", excerpt="Synthetic notes", course_id="contract-course", url="https://www.learn.ed.ac.uk/ultra/courses/_1_1/file/_3_1"),
        Item(native_id="contract-date", kind="assignment", title="Date-only exercise", excerpt="Date-only exercise", due_date="2030-10-21"),
        Item(native_id="contract-unknown", kind="assignment", title="Undated exercise", excerpt="Undated exercise"),
    ]
    receipt = database.capture(Observation(source="learn", source_url="https://www.learn.ed.ac.uk/ultra/courses/_1_1/outline", title="Contract fixture", observed_at=now_utc(), scope="Synthetic contract-test records", text="\n".join(row.excerpt for row in records), items=records))
    return {row["native_id"]: row for row in database.items_by_ids(receipt["inserted"])}


def download_fixture(database, key):
    payload = ("Synthetic lecture text.\n" * 80).encode()
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload, headers={"content-type": "text/plain"}))) as client:
        receipt = downloads.download_resource(database, key, "https://www.learn.ed.ac.uk/content/synthetic.txt", "synthetic.txt", client=client)
    assert Path(receipt["path"]).read_bytes() == payload
    return receipt, payload


def job_receipt(database, state="complete", *, action="courses", result=None):
    identifier = uuid.uuid4().hex
    value = {"job_id": identifier, "action": action, "state": state, "updated_at": now_utc().isoformat(), "progress": "Synthetic job state"}
    if result is not None:
        value["result"] = result
    school.write_json(school.job_path(database, identifier), value)
    return identifier


def replace_result(module, monkeypatch, name, change):
    """Inject at a known backend boundary; keep registration/argument metadata intact."""
    entry = module.mcp._tool_manager.get_tool(name)
    original = entry.fn

    def changed(**kwargs):
        reply = original(**kwargs)
        value = deepcopy(reply.structuredContent)
        change(value)
        return module.result(value, "full")

    monkeypatch.setattr(entry, "fn", changed)


def timetable_export():
    headers = ["Title", "Type", "Date", "Day of the Week", "Start Time", "End Time", "Location", "Weeks"]
    rows = [
        ["Algebra", "Lecture", "Mon, 19th October 2026", "Monday", "09:00", "09:50", "Room A", "(2026/7) S1 Wk 5"],
        ["Algebra", "Lecture", "Mon, 26th October 2026", "Monday", "09:00", "09:50", "Room A", "(2026/7) S1 Wk 6"],
    ]
    return "<table><tr>" + "".join("<th>" + cell + "</th>" for cell in headers) + "</tr>" + "".join("<tr>" + "".join("<td>" + cell + "</td>" for cell in row) + "</tr>" for row in rows) + "</table>"


def test_all_profiles_advertise_valid_output_contracts_and_discover_advanced_operations(profiles):
    load, _ = profiles
    names = set()
    for profile, count in (("full", 38), ("student", 35), ("daily", 15)):
        module = load(profile)
        catalog = asyncio.run(module.mcp.list_tools())
        assert len(catalog) == count
        names.update(tool.name for tool in catalog)
        for tool in catalog:
            assert tool.outputSchema and tool.outputSchema.get("type") == "object"
            Draft202012Validator.check_schema(tool.outputSchema)
            assert not Draft202012Validator(tool.outputSchema).is_valid({}), tool.name
        if profile != "daily":
            continue
        advanced = [entry.name for entry in module.mcp._tool_manager.list_tools() if entry.name not in module.mcp.visible_tools]
        assert len(advanced) == 21
        for operation in advanced:
            reply = success(call(module, "study_more", {"mode": "describe", "tool": operation}), "study_more")
            assert reply["tool"] == operation and reply["contract_version"] == "1"
            assert reply["outputSchema"] == contracts.output_schema(operation)
            Draft202012Validator.check_schema(reply["outputSchema"])
        # Detailed operation shapes are discovered on demand, not multiplied into the dispatcher.
        dispatcher = next(tool for tool in catalog if tool.name == "study_more")
        assert len(json.dumps(dispatcher.outputSchema)) < 8000
    assert len(names) == 39


def test_schema_help_is_on_demand_and_describes_a_real_operation(profiles):
    load, _ = profiles
    module = load("daily")
    body = success(call(module, "study_help", {"topic": "schemas", "tool": "study_task_create"}), "study_help")
    assert body["topic"] == "schemas" and body["presentation"]
    serialized = json.dumps(body["guidance"])
    assert "study_task_create" in serialized and "outputSchema" in serialized
    assert "estimate_minutes" in serialized and "local_only" in serialized
    ordinary = success(call(module, "study_help"), "study_help")
    assert "outputSchema" not in json.dumps(ordinary)


@pytest.mark.parametrize("profile", ["full", "daily"])
def test_basic_queries_keep_dated_data_unknown_dates_and_text_fallback(profiles, profile):
    load, database = profiles
    module = load(profile)
    rows = seed(database)
    status = success(call(module, "study_status"), "study_status")
    assert status["counts"]["course"] == 1 and status["counts"]["assignment"] == 2
    assert status["live_connection_checked"] is False
    found = success(call(module, "study_search", {"kind": "course", "limit": 1}), "study_search")
    assert found["total_matches"] == 1 and found["items"][0]["title"] == "Synthetic Algebra"
    assert found["items"][0]["observation_id"] == rows["contract-course"]["observation_id"]
    empty = success(call(module, "study_search", {"query": "No such synthetic course"}), "study_search")
    assert empty["items"] == [] and empty["total_matches"] == 0
    timeline = success(call(module, "study_agenda", {"start": "2030-10-21", "end": "2030-10-21"}), "study_agenda")
    assert timeline["unknown_dates"] == 1 and timeline["coverage"] == "cached_observations_only"
    by_title = {row["title"]: row for row in timeline["items"]}
    assert by_title["Date-only exercise"]["timing"] == "date_only"
    assert by_title["Date-only exercise"]["due_date"] == "2030-10-21"
    assert by_title["Date-only exercise"].get("due_at") is None
    assert by_title["Undated exercise"]["timing"] == "unknown"


def test_direct_and_dispatch_results_share_operations_and_unchanged_data(profiles):
    load, database = profiles
    full, daily = load("full"), load("daily")
    rows = seed(database)
    task = success(call(daily, "study_more", {"mode": "call", "tool": "study_task_create", "arguments": {"title": "Read notes", "estimate_minutes": 30}}), "study_task_create")
    assert task["title"] == "Read notes" and task["status"] == "todo" and task["local_only"]
    saved = success(call(daily, "study_more", {"mode": "call", "tool": "study_collect", "arguments": {"item_id": rows["contract-file"]["id"], "tags": ["revision"]}}), "study_collect")
    assert saved["university_record_changed"] is False
    for name in ("study_tasks", "study_collections"):
        direct = success(call(full, name), name)
        dispatched = success(call(daily, "study_more", {"mode": "call", "tool": name}), name)
        assert direct == dispatched
    assert len(database.tasks()["tasks"]) == 1
    closed = success(call(daily, "study_more", {"mode": "call", "tool": "study_task_update", "arguments": {"task_id": task["id"], "status": "done"}}), "study_task_update")
    assert closed["task"]["status"] == "done" and closed["university_submission_changed"] is False


@pytest.mark.parametrize("dispatched", [False, True])
@pytest.mark.parametrize("arguments", [
    {"title": "Safe title", "estimate_minutes": "private-value-sentinel"},
    {"title": "Safe title", "estimate_minutes": 1},
    {"title": "Safe title", "estimate_minutes": 30, "priority": 9},
    {"title": "password=private-value-sentinel", "estimate_minutes": 30},
])
def test_invalid_arguments_are_structured_redacted_and_do_not_write(profiles, dispatched, arguments):
    load, database = profiles
    module = load("daily" if dispatched else "full")
    name = "study_more" if dispatched else "study_task_create"
    request = {"mode": "call", "tool": "study_task_create", "arguments": arguments} if dispatched else arguments
    reply = call(module, name, request)
    body = failure(reply, "study_task_create", "INVALID_ARGUMENT")
    assert "private-value-sentinel" not in json.dumps(body)
    assert database.tasks()["tasks"] == []


def test_unknown_tool_and_runtime_errors_are_structured_without_leaking_values(profiles, monkeypatch):
    load, _ = profiles
    module = load()
    unknown = call(module, "study_missing", {})
    assert unknown.isError and unknown.structuredContent["error"]["code"] == "UNKNOWN_TOOL"
    entry = module.mcp._tool_manager.get_tool("study_status")
    def broken(**kwargs):
        raise RuntimeError("https://example.invalid/?access_token=private-value-sentinel")
    monkeypatch.setattr(entry, "fn", broken)
    body = failure(call(module, "study_status"), "study_status", "TOOL_ERROR")
    assert "private-value-sentinel" not in json.dumps(body)
    assert "example.invalid" not in json.dumps(body)


def test_malformed_backend_success_is_rejected_at_public_boundary(profiles, monkeypatch):
    load, _ = profiles
    module = load()
    replace_result(module, monkeypatch, "study_status", lambda body: body.update(counts={"course": "private-value-sentinel"}))
    body = failure(call(module, "study_status"), "study_status", "OUTPUT_VALIDATION_ERROR")
    assert "private-value-sentinel" not in json.dumps(body)


def test_format_failure_after_task_write_keeps_identifier_and_never_retries(profiles, monkeypatch):
    load, database = profiles
    module = load("daily")
    entry = module.mcp._tool_manager.get_tool("study_task_create")
    original = entry.fn
    calls = []
    def malformed(**kwargs):
        reply = original(**kwargs)
        calls.append(reply.structuredContent["id"])
        reply.structuredContent["estimate_minutes"] = {"wrong": "type"}
        return module.result(reply.structuredContent, "full")
    monkeypatch.setattr(entry, "fn", malformed)
    body = failure(call(module, "study_more", {"mode": "call", "tool": "study_task_create", "arguments": {"title": "Created exactly once", "estimate_minutes": 30}}), "study_task_create", "OUTPUT_VALIDATION_ERROR")
    assert len(calls) == 1 and calls[0] in body["identifiers"].values()
    persisted = database.tasks()["tasks"]
    assert len(persisted) == 1 and persisted[0]["estimate_minutes"] == 30


def test_format_failure_after_job_creation_keeps_job_id_and_never_retries(profiles, monkeypatch):
    load, database = profiles
    module = load()
    entry = module.mcp._tool_manager.get_tool("study_live_courses")
    calls = []
    def malformed(**kwargs):
        key = job_receipt(database, result={"live": True, "items": [], "coverage": "partial"})
        calls.append(key)
        reply = school.read_job(database, key)
        reply["result"]["items"] = "private-value-sentinel"
        return module.result(reply, "full")
    monkeypatch.setattr(entry, "fn", malformed)
    body = failure(call(module, "study_live_courses"), "study_live_courses", "OUTPUT_VALIDATION_ERROR")
    assert calls == [body["identifiers"]["job_id"]]
    assert len(list((database.root / "school/jobs").glob("*.json"))) == 1
    assert school.read_job(database, calls[0])["result"]["items"] == []
    assert "private-value-sentinel" not in json.dumps(body)


@pytest.mark.parametrize("state", ["queued", "running", "waiting_for_login", "complete", "partial", "needs_login", "failed", "cancelled"])
def test_job_lifecycle_preserves_status_and_does_not_fabricate_results(profiles, state):
    load, database = profiles
    module = load()
    result = {"live": True, "items": [], "coverage": "partial", "warning": "No supported course cards observed"} if state in {"complete", "partial"} else None
    key = job_receipt(database, state, result=result)
    body = success(call(module, "study_school_job", {"job_id": key, "wait_seconds": 0, "detail": "full"}), "study_school_job")
    assert body["state"] == state and body["job_id"] == key
    assert body["poll_after_seconds"] == (0 if state in school.TERMINAL else 3)
    assert ("result" in body) == (result is not None)


def test_unchanged_job_poll_omits_results_and_rejects_unknown_state(profiles):
    load, database = profiles
    module = load()
    key = job_receipt(database, "running")
    stamp = school.read_job(database, key)["updated_at"]
    body = success(call(module, "study_school_job", {"job_id": key, "wait_seconds": 0, "if_updated_at": stamp}), "study_school_job")
    assert body["unchanged"] and "result" not in body and "action" not in body
    bad = deepcopy(body)
    bad["state"] = "apparently-done"
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_school_job", bad)


def test_file_metadata_and_paginated_text_keep_verified_bytes_and_null_semantics(profiles):
    load, database = profiles
    module = load()
    key = seed(database)["contract-file"]["id"]
    receipt, payload = download_fixture(database, key)
    listed = success(call(module, "study_downloads", {"item_id": key}), "study_downloads")
    record = listed["files"][0]
    assert record["size_bytes"] == len(payload) and record["sha256"] == downloads.digest_file(Path(record["path"]))
    assert record["item_id"] == key and listed["signed_urls_stored"] is False
    first = success(call(module, "study_read_file", {"item_id": key, "max_chars": 500}), "study_read_file")
    assert first["verified"] and first["sha256"] == receipt["sha256"] and first["next_offset"] == 500
    final = success(call(module, "study_read_file", {"item_id": key, "offset": 500, "max_chars": 30000}), "study_read_file")
    assert not final["has_more"] and final["next_offset"] is None
    assert first["text"] + final["text"] == "\n[text]\n" + payload.decode()
    bad = deepcopy(listed)
    bad["files"][0]["size_bytes"] = -1
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_downloads", bad)
    bad = deepcopy(final)
    bad["next_offset"] = "unknown"
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_read_file", bad)


@pytest.mark.parametrize("view,year,expected", [("summary", "2026/27", 1), ("occurrences", "2026/27", 2), ("summary", "2027/28", 0)])
def test_timetable_branches_keep_dates_dst_and_missing_year_scope(profiles, view, year, expected):
    load, database = profiles
    module = load()
    workflow_cache.put(database, "timetable", "personal", timetable.parse_export(timetable_export()))
    body = success(call(module, "study_timetable", {"academic_year": year, "semester": 1, "view": view}), "study_timetable")
    result = body["result"]
    assert len(result["items"]) == expected and result["remote_freshness_checked"] is False
    if year == "2027/28":
        assert body["state"] == "partial" and result["coverage"] == "partial"
        assert result["overview"]["first_class_date"] is None
    elif view == "summary":
        assert result["items"][0]["dates"] == ["2026-10-19", "2026-10-26"]
    else:
        assert result["items"][0]["starts_at"].endswith("+01:00")
        assert result["items"][1]["starts_at"].endswith("+00:00")
    damaged = deepcopy(body)
    damaged["result"]["occurrence_count"] = "two"
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_timetable", damaged)
    damaged["_contract"]["operation"] = "study_school_job"
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_school_job", damaged)


@pytest.mark.parametrize("operation", ["list", "read", "download"])
def test_materials_actions_share_verified_cache_without_browser(profiles, operation):
    load, database = profiles
    module = load()
    key = seed(database)["contract-file"]["id"]
    receipt, _ = download_fixture(database, key)
    body = success(call(module, "study_materials", {"item_id": key, "operation": operation}), "study_materials")
    result = body["result"]
    assert body["browser_started"] is False and result["remote_freshness_checked"] is False
    if operation == "list":
        assert result["items"][0]["id"] == key and result["coverage"] == "partial"
    elif operation == "read":
        assert result["content"]["sha256"] == receipt["sha256"] and result["content"]["verified"]
    else:
        assert result["saved"][0]["sha256"] == receipt["sha256"] and result["failed"] == []
    damaged = deepcopy(body)
    if operation == "list": damaged["result"]["items"][0]["title"] = 99
    elif operation == "read": damaged["result"]["content"]["verified"] = "yes"
    else: damaged["result"]["saved"][0]["sha256"] = None
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_materials", damaged)


def test_results_keep_blank_and_zero_marks_without_invented_grade_values(profiles):
    from edinburgh_study_agent import results
    load, database = profiles
    module = load()
    class Page:
        def evaluate(self, script):
            return [dict(academic_year="2026/27", panel_found=True, selected=True, block_count=1, records=[dict(title="Current - TEST10001", mark="", grade="", credits="20", result="", sit="")]), dict(academic_year="2025/26", panel_found=True, selected=False, block_count=1, records=[dict(title="Previous - TEST08001", mark="0", grade="F", credits="20", result="Published", sit="1")])]
    results.read_results(database, Page())
    body = success(call(module, "study_results"), "study_results")
    assert body["state"] == "complete" and [row["mark"] for row in body["result"]["items"]] == ["", "0"]
    damaged = deepcopy(body)
    damaged["result"]["items"][0]["mark"] = 0
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_results", damaged)


def test_message_counters_keep_zero_separate_from_unknown_and_history(profiles):
    load, database = profiles
    module = load()
    data = dict(items=[dict(title="Algebra", course_code="ALG101", unread_text="0 unread", unread_count=0, url="https://www.learn.ed.ac.uk/ultra/messages"), dict(title="Geometry", course_code="GEO101", unread_text="", unread_count=None, url="https://www.learn.ed.ac.uk/ultra/messages")], source_url="https://www.learn.ed.ac.uk/ultra/messages", observed_at=now_utc().isoformat(), coverage="partial", scope="Unread counters are not message history.", view="inboxes")
    workflow_cache.put(database, "learn_updates", "inboxes", data)
    body = success(call(module, "study_messages", {"view": "inboxes"}), "study_messages")
    assert body["result"]["items"][0]["unread_count"] == 0
    assert body["result"]["items"][1]["unread_count"] is None
    assert body["state"] == "partial" and "not message history" in body["result"]["scope"]
    damaged = deepcopy(body)
    damaged["result"]["items"][1]["unread_count"] = "none"
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_messages", damaged)


def test_public_event_dates_preserve_unknowns_and_independent_source_failures(profiles, monkeypatch):
    from edinburgh_study_agent import campus_events
    load, _ = profiles
    module = load()
    def fetch(url):
        if url == campus_events.PHYSICS:
            raise TimeoutError("Synthetic unavailable source")
        if url == campus_events.SEMESTERS:
            return '<a href="/202627">2026/27</a>'
        return '<table><tr><td>6-8 January 2027</td><td>January Welcome</td></tr><tr><td>Date unknown</td><td>Undated event</td></tr></table>'
    monkeypatch.setattr(campus_events, "fetch", fetch)
    body = success(call(module, "study_events", {"academic_year": "2026/27"}), "study_events")
    assert body["undated_records"] == 1 and body["coverage"] == "partial"
    items = {item["title"]: item for item in body["items"]}
    assert (items["January Welcome"]["start_date"], items["January Welcome"]["end_date"]) == ("2027-01-06", "2027-01-08")
    assert items["Undated event"]["start_date"] is None
    physics = next(row for row in body["sources"] if row["source"] == "physics_events")
    assert physics["record_count"] == 0 and physics["coverage"] == "unavailable"
    damaged = deepcopy(body)
    damaged["items"][0]["start_date"] = 0
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_events", damaged)

@pytest.mark.parametrize("damage", ["no_action", "no_result", "null_result", "wrong_action"])
def test_completed_job_cannot_hide_missing_or_mismatched_action_payload(profiles, damage):
    load, database = profiles
    module = load()
    key = job_receipt(database, result={"live": True, "items": [], "coverage": "partial", "warning": "No course cards"})
    body = success(call(module, "study_school_job", {"job_id": key, "wait_seconds": 0}), "study_school_job")
    if damage == "no_action":
        body.pop("action")
        body.pop("result")
    elif damage == "no_result":
        body.pop("result")
    elif damage == "null_result":
        body["result"] = None
    else:
        body["action"] = "download"
    with pytest.raises(contracts.OutputValidationError):
        contracts.validate_result("study_school_job", body)


@pytest.mark.parametrize("payload", [float("nan"), float("inf"), ["not a result object"]])
def test_non_json_or_nonfinite_backend_data_is_an_output_error(profiles, monkeypatch, payload):
    load, _ = profiles
    module = load()
    entry = module.mcp._tool_manager.get_tool("study_status")
    original = entry.fn
    def malformed(**kwargs):
        if isinstance(payload, list):
            return payload
        body = original(**kwargs).structuredContent
        body["counts"]["course"] = payload
        return CallToolResult(content=[], structuredContent=body)
    monkeypatch.setattr(entry, "fn", malformed)
    failure(call(module, "study_status"), "study_status", "OUTPUT_VALIDATION_ERROR")


def test_media_and_resource_blocks_survive_structured_text_fallback(profiles, monkeypatch):
    from mcp.types import ImageContent, ResourceLink, TextContent
    load, _ = profiles
    module = load()
    entry = module.mcp._tool_manager.get_tool("study_status")
    original = entry.fn
    media = [
        ImageContent(type="image", mimeType="image/png", data="c3ludGhldGlj"),
        ResourceLink(type="resource_link", name="Synthetic artifact", uri="https://example.invalid/synthetic.txt", mimeType="text/plain", size=9),
    ]
    def with_media(**kwargs):
        reply = original(**kwargs)
        return reply.model_copy(update={"content": [*reply.content, *media, TextContent(type="text", text="Synthetic explanation")]})
    monkeypatch.setattr(entry, "fn", with_media)
    reply = call(module, "study_status")
    assert not reply.isError
    assert json.loads(reply.content[0].text) == reply.structuredContent
    assert reply.content[1:3] == media
    assert reply.content[3].text == "Synthetic explanation"
    assert "c3ludGhldGlj" not in json.dumps(reply.structuredContent)


def test_valid_structured_error_gets_json_fallback_and_retains_media(profiles, monkeypatch):
    from mcp.types import ImageContent, ResourceLink, TextContent
    load, _ = profiles
    module = load()
    entry = module.mcp._tool_manager.get_tool("study_status")
    body = {
        "contract_version": "1",
        "error": {
            "code": "TOOL_ERROR", "operation": "study_status",
            "message": "Synthetic backend failure.",
            "recovery": "Inspect the existing operation before retrying.",
        },
    }
    media = [
        ImageContent(type="image", mimeType="image/png", data="c3ludGhldGlj"),
        ResourceLink(type="resource_link", name="Synthetic diagnostic", uri="https://example.invalid/diagnostic.txt", mimeType="text/plain", size=9),
    ]
    def legacy_error(**kwargs):
        return CallToolResult(isError=True, structuredContent=body, content=[TextContent(type="text", text="Legacy free-text error without JSON"), *media])
    monkeypatch.setattr(entry, "fn", legacy_error)
    reply = call(module, "study_status")
    delivered = failure(reply, "study_status", "TOOL_ERROR")
    assert delivered == body
    assert [block for block in reply.content if block.type != "text"] == media
    assert len([block for block in reply.content if block.type == "text"]) == 1


@pytest.mark.parametrize("operation", ["study_capture", "study_import_calendar"])
def test_bad_capture_or_import_result_retains_saved_observation_id(profiles, monkeypatch, operation):
    load, database = profiles
    module = load()
    if operation == "study_capture":
        observation = Observation(source="learn", source_url="https://www.learn.ed.ac.uk/ultra/courses/_1_1/outline", title="Saved synthetic observation", observed_at=now_utc(), scope="Synthetic write-failure regression", text="Saved synthetic observation")
        arguments = {"observation": observation.model_dump(mode="json")}
    else:
        path = database.root / "synthetic-import.ics"
        path.write_text("BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Synthetic regression//EN\nBEGIN:VEVENT\nUID:output-contract-import\nSUMMARY:Synthetic class\nDTSTART:20301021T090000Z\nDTEND:20301021T100000Z\nEND:VEVENT\nEND:VCALENDAR\n", encoding="utf-8")
        arguments = {"file_path": str(path), "source": "timetable", "source_url": "https://timetabler.is.ed.ac.uk/", "start": "2030-10-21", "end": "2030-10-21"}
    entry = module.mcp._tool_manager.get_tool(operation)
    original = entry.fn
    saved = []
    def malformed(**kwargs):
        reply = original(**kwargs)
        saved.append(reply.structuredContent["observation_id"])
        reply.structuredContent["duplicate"] = "not a boolean"
        return module.result(reply.structuredContent, "full")
    monkeypatch.setattr(entry, "fn", malformed)
    body = failure(call(module, operation, arguments), operation, "OUTPUT_VALIDATION_ERROR")
    assert saved == [body["identifiers"]["observation_id"]]
    with database.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    evidence = database.evidence(saved[0])["observation"]
    assert evidence["source"] == ("learn" if operation == "study_capture" else "timetable")
    if operation == "study_import_calendar":
        assert len(evidence["items"]) == 1 and evidence["items"][0]["title"] == "Synthetic class"


@pytest.mark.parametrize("message", ["password : PRIVATE_SENTINEL", "token = PRIVATE_SENTINEL", "api_key : PRIVATE_SENTINEL"])
def test_value_error_redaction_handles_whitespace_around_secret_delimiters(profiles, monkeypatch, message):
    load, _ = profiles
    module = load()
    entry = module.mcp._tool_manager.get_tool("study_status")
    def invalid(**kwargs):
        raise ValueError(message)
    monkeypatch.setattr(entry, "fn", invalid)
    reply = call(module, "study_status")
    body = failure(reply, "study_status", "INVALID_ARGUMENT")
    assert "PRIVATE_SENTINEL" not in json.dumps(body)
    assert all("PRIVATE_SENTINEL" not in block.text for block in reply.content if block.type == "text")


@pytest.mark.parametrize("dispatched", [False, True])
def test_non_json_value_after_task_write_reaches_output_boundary_with_id(profiles, monkeypatch, dispatched):
    load, database = profiles
    module = load("daily" if dispatched else "full")
    entry = module.mcp._tool_manager.get_tool("study_task_create")
    original = entry.fn
    saved = []
    def malformed(**kwargs):
        reply = original(**kwargs)
        saved.append(reply.structuredContent["id"])
        reply.structuredContent["notes"] = Path("synthetic/non-json-value")
        return module.result(reply.structuredContent, "full")
    monkeypatch.setattr(entry, "fn", malformed)
    arguments = {"title": "Preserve this single task", "estimate_minutes": 30}
    reply = call(module, "study_more", {"mode": "call", "tool": "study_task_create", "arguments": arguments}) if dispatched else call(module, "study_task_create", arguments)
    body = failure(reply, "study_task_create", "OUTPUT_VALIDATION_ERROR")
    assert len(saved) == 1 and saved[0] in body["identifiers"].values()
    tasks = database.tasks()["tasks"]
    assert len(tasks) == 1 and tasks[0]["id"] == saved[0] and tasks[0]["notes"] == ""


def test_worker_launch_failure_returns_saved_failed_job_without_retry(profiles, monkeypatch):
    load, database = profiles
    module = load()
    attempts = []
    def unavailable(*args, **kwargs):
        attempts.append(1)
        raise OSError("Synthetic process failure PRIVATE_SENTINEL")
    monkeypatch.setattr(school.subprocess, "Popen", unavailable)
    body = success(call(module, "study_live_courses"), "study_live_courses")
    assert body["state"] == "failed" and body["poll_after_seconds"] == 0
    assert "result" not in body and attempts == [1]
    path = school.job_path(database, body["job_id"])
    assert len(list(path.parent.glob("*.json"))) == 1
    persisted = school.read_job(database, body["job_id"])
    assert persisted["job_id"] == body["job_id"] and persisted["state"] == "failed"
    assert "PRIVATE_SENTINEL" not in path.read_text(encoding="utf-8")
    assert "PRIVATE_SENTINEL" not in json.dumps(body)


@pytest.mark.parametrize("profile", ["full", "student", "daily"])
def test_mixed_download_catalog_normalizes_legacy_nmr_without_rewriting(profiles, profile):
    load, database = profiles
    module = load(profile)
    key = seed(database)["contract-file"]["id"]
    saved, payload = download_fixture(database, key)
    legacy = {k:v for k,v in saved.items() if k not in
              {"title","reused","verified","signed_urls_stored","save_dialog_required"}}
    legacy["item_id"] = "synthetic-nmr"
    legacy["filename"] = "Synthetic-acquisition.zip"
    raw = json.dumps(legacy)
    with database.connection() as db:
        db.execute("INSERT INTO downloads VALUES(?,?,?,?)",
                   (legacy["item_id"],legacy["sha256"],legacy["downloaded_at"],raw))
    if profile == "daily":
        reply = call(module,"study_more",{"mode":"call","tool":"study_downloads","arguments":{}})
    else:
        reply = call(module,"study_downloads",{})
    listed = success(reply,"study_downloads")
    assert len(listed["files"]) == 2
    fixed = next(r for r in listed["files"] if r["item_id"] == "synthetic-nmr")
    assert fixed["title"] == legacy["filename"] and fixed["title_source"] == "filename"
    with database.connection() as db:
        assert db.execute("SELECT payload FROM downloads WHERE item_id=?",("synthetic-nmr",)).fetchone()[0] == raw
    assert Path(saved["path"]).read_bytes() == payload


def test_output_required_failure_names_schema_field_without_private_values(profiles, monkeypatch):
    load, database = profiles
    module = load()
    key = seed(database)["contract-file"]["id"]
    saved, _ = download_fixture(database,key)
    bad = {**saved,"file_exists":True,"title":"PRIVATE_TITLE_SENTINEL"}
    del bad["source_page_url"]
    monkeypatch.setattr(module,"list_downloads",lambda *_: {"files":[bad],"signed_urls_stored":False})
    result = failure(call(module,"study_downloads",{}),"study_downloads","OUTPUT_VALIDATION_ERROR")
    assert "source_page_url" in result["error"]["message"]
    assert "PRIVATE_TITLE_SENTINEL" not in json.dumps(result)
