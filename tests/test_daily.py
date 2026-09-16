import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from edinburgh_study_agent import hosts, timetable, workflow_cache
from edinburgh_study_agent.models import now_utc
from edinburgh_study_agent.store import Store


def test_daily_real_mcp_discovery_call_validation_and_no_legacy_bypass(tmp_path):
    config = hosts.server_config(sys.executable, tmp_path / "private", profile="daily")
    async def run():
        async with stdio_client(StdioServerParameters(command=config["command"], args=config["args"], env=config["env"])) as (r, w):
            async with ClientSession(r, w) as session:
                init = await session.initialize()
                assert "study_more" in init.instructions
                tools = (await session.list_tools()).tools
                assert len(tools) == 15 and {"study_materials", "study_nmr"} <= {t.name for t in tools}
                assert "study_task_create" not in {t.name for t in tools}
                found = await session.call_tool("study_more", {"query": "task"})
                assert not found.isError
                description = await session.call_tool("study_more", {"mode": "describe", "tool": "study_task_create"})
                assert "estimate_minutes" in description.structuredContent["inputSchema"]["properties"]
                invalid = await session.call_tool("study_more", {"mode": "call", "tool": "study_task_create", "arguments": {"title": "Synthetic", "estimate_minutes": 1}})
                assert invalid.isError
                created = await session.call_tool("study_more", {"mode": "call", "tool": "study_task_create", "arguments": {"title": "Synthetic", "estimate_minutes": 30}})
                assert not created.isError
                listed = await session.call_tool("study_more", {"mode": "call", "tool": "study_tasks"})
                assert len(listed.structuredContent["tasks"]) == 1
                forbidden = await session.call_tool("study_more", {"mode": "call", "tool": "study_capture", "arguments": {}})
                assert forbidden.isError
    asyncio.run(run())


def test_document_previews_are_explicit_and_exact_week_cells_are_recoverable(tmp_path, monkeypatch):
    store = Store(tmp_path)
    text = "09:00-09:50 Example lecture\n" * 18
    saved = {"path": "synthetic.pdf", "filename": "synthetic.pdf", "sha256": "synthetic", "source_page_url": "https://learn.ed.ac.uk/"}
    monkeypatch.setattr(timetable, "verified_copy", lambda store, key: saved)
    data = {"weeks": [{"semester": 1, "week": n, "pages": [n], "days": {"Mon": text + str(n)}} for n in (1, 2)],
            "scope": "Course grid", "date_mapping": "No dates inferred", "problems": []}
    workflow_cache.put(store, "pdf_layout", "v2:synthetic", data)
    preview = timetable.document(store, {"item_id": "synthetic", "semester": 1})
    full = timetable.document(store, {"item_id": "synthetic", "semester": 1, "week": 2, "view": "occurrences"})
    assert preview["view"] == "week_previews" and len(preview["items"]) == 2
    assert preview["items"][0]["truncated_days"] == ["Mon"]
    assert full["items"][0]["days"]["Mon"] == text + "2"
    assert len(full["items"]) == 1 and full["view"] == "week_cells"


def test_identical_cached_reads_reuse_receipt_but_changed_source_does_not(tmp_path, monkeypatch):
    from edinburgh_study_agent import school
    store = Store(tmp_path)
    cached = {"items": [], "observed_at": "2030-01-01T00:00:00Z", "coverage": "partial"}
    monkeypatch.setattr(school, "cached_operation", lambda *args: cached)
    first = school.start_job(store, "messages", {"view": "activity"})
    repeat = school.start_job(store, "messages", {"view": "activity"})
    assert repeat["reused_cached_job"] and repeat["job_id"] == first["job_id"]
    assert repeat["state"] == "partial" and repeat["result"] == first["result"]
    assert len(list((tmp_path / "school/jobs").glob("*.json"))) == 1
    cached["observed_at"] = "2030-01-01T00:01:00Z"
    changed = school.start_job(store, "messages", {"view": "activity"})
    assert changed["job_id"] != first["job_id"]
