"""Behavioral checks for verified, host-neutral course-file delivery."""
import base64
import hashlib
import io
import json
import random
import zipfile
from pathlib import Path

import httpx
import pytest

from edinburgh_study_agent.delivery import export_files
from edinburgh_study_agent.downloads import download_resource, list_downloads
from edinburgh_study_agent.models import Item, Observation, now_utc
from edinburgh_study_agent.store import Store


SIGNED_URL = (
    "https://prod01-euc1-prod01-xythos.prod.files.blackboard.com/example"
    "?X-Amz-Signature=SYNTHETIC_DO_NOT_EXPORT"
)
PDF = b"%PDF-1.7\nSynthetic transfer fixture\n"


@pytest.fixture
def cached_resource(tmp_path):
    store = Store(tmp_path / "private")
    counter = 0

    def create(body=PDF, filename="handout.pdf", *, source="learn", kind="resource"):
        nonlocal counter
        counter += 1
        title = f"Synthetic resource {counter}"
        source_url = (
            "https://www.learn.ed.ac.uk/ultra/course"
            if source == "learn"
            else "https://www.myed.ed.ac.uk/student"
        )
        observation = Observation(
            source=source, source_url=source_url, title=title,
            observed_at=now_utc(), scope="synthetic", text=title,
            items=[Item(native_id=f"resource-{counter}", kind=kind, title=title,
                        excerpt=title, course_id="synthetic-course")],
        )
        item_id = store.capture(observation)["inserted"][0]
        if body is None:
            return item_id, None
        with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body)
        )) as client:
            record = download_resource(store, item_id, SIGNED_URL, filename, client=client)
        return item_id, record

    return store, create


def resources(result):
    return [entry.resource for entry in result.content if entry.type == "resource"]


def raw_resource(resource):
    return base64.b64decode(resource.blob, validate=True)


def change_download_record(store, item_id, **changes):
    record = list_downloads(store, item_id)["files"][0]
    record.update(changes)
    with store.connection() as db:
        db.execute("UPDATE downloads SET payload=? WHERE item_id=?",
                   (json.dumps(record), item_id))


def synthetic_xlsx():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
    return stream.getvalue()


@pytest.mark.parametrize("body,filename,mime", [
    (PDF, "handout.pdf", "application/pdf"),
    (synthetic_xlsx(), "past papers.xlsx",
     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
], ids=["pdf", "xlsx"])
def test_export_supplies_original_bytes_not_only_windows_path(cached_resource, body, filename, mime):
    store, create = cached_resource
    item_id, _ = create(body, filename)
    result = export_files(store, [item_id], mode="files")
    receipt = result.structuredContent
    exported = resources(result)
    digest = hashlib.sha256(body).hexdigest()
    assert receipt["state"] == "awaiting_host_receipt"
    assert receipt["host_registration"] == "required"
    assert receipt["files"][0]["sha256"] == digest
    assert receipt["files"][0]["size_bytes"] == len(body)
    assert receipt["files"][0]["filename"] == filename
    assert receipt["total_bytes"] == len(body)
    assert len(exported) == 1
    assert raw_resource(exported[0]) == body
    assert exported[0].mimeType == mime
    assert str(exported[0].uri) == receipt["payloads"][0]["resource_uri"]
    text = next(entry.text for entry in result.content if entry.type == "text")
    assert json.loads(text) == receipt
    assert base64.b64encode(body).decode() not in text


def test_manifest_is_metadata_only_and_does_not_claim_host_delivery(cached_resource):
    store, create = cached_resource
    item_id, _ = create()
    result = export_files(store, [item_id], mode="manifest")
    receipt = result.structuredContent
    assert not resources(result)
    assert receipt["payloads"] == []
    assert receipt["state"] == "verified_local"
    assert receipt["host_registration"] == "not_requested"
    assert receipt["files"][0]["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert receipt["total_bytes"] == len(PDF)


def test_bundle_preserves_same_name_files_and_manifest_and_is_repeatable(cached_resource):
    store, create = cached_resource
    first_body, second_body = PDF, PDF + b"Second independent original\n"
    first, _ = create(first_body, "same name.pdf")
    second, _ = create(second_body, "same name.pdf")
    before = {path.relative_to(store.root) for path in store.root.rglob("*")}
    result = export_files(store, [first, second], mode="bundle")
    repeated = export_files(store, [first, second], mode="bundle")
    blob = raw_resource(resources(result)[0])
    assert raw_resource(resources(repeated)[0]) == blob
    assert result.structuredContent["export_id"] == repeated.structuredContent["export_id"]
    assert result.structuredContent["payloads"][0]["sha256"] == hashlib.sha256(blob).hexdigest()
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == ["01/same name.pdf", "02/same name.pdf", "manifest.json"]
        assert archive.read("01/same name.pdf") == first_body
        assert archive.read("02/same name.pdf") == second_body
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["export_id"] == result.structuredContent["export_id"]
        for row, item_id, body in zip(manifest["files"], [first, second], [first_body, second_body]):
            assert row["item_id"] == item_id
            assert row["sha256"] == hashlib.sha256(body).hexdigest()
            assert archive.read(row["bundle_path"]) == body
    assert {path.relative_to(store.root) for path in store.root.rglob("*")} == before


@pytest.mark.parametrize("mode", ["manifest", "files", "bundle"])
def test_export_does_not_leak_signed_urls_local_paths_or_fabricate_host_ids(cached_resource, mode):
    store, create = cached_resource
    item_id, record = create()
    change_download_record(store, item_id, download_url=SIGNED_URL,
                           file_id="file_forged_not_a_host_receipt", file_uri="fake-host-reference")
    result = export_files(store, [item_id], mode=mode)
    visible = result.model_dump_json()
    if mode == "bundle":
        with zipfile.ZipFile(io.BytesIO(raw_resource(resources(result)[0]))) as archive:
            visible += archive.read("manifest.json").decode()
    for forbidden in ("SYNTHETIC_DO_NOT_EXPORT", "file_forged_not_a_host_receipt",
                      "fake-host-reference", str(store.root), record["path"]):
        assert forbidden not in visible
        assert json.dumps(forbidden, ensure_ascii=False)[1:-1] not in visible
    assert '"file_id"' not in visible
    assert '"download_url"' not in visible


@pytest.mark.parametrize("damage", ["missing", "empty", "truncated", "same_size_tampered"])
def test_export_rejects_missing_or_modified_cached_original(cached_resource, damage):
    store, create = cached_resource
    item_id, record = create()
    path = Path(record["path"])
    if damage == "missing":
        path.unlink()
    elif damage == "empty":
        path.write_bytes(b"")
    elif damage == "truncated":
        path.write_bytes(PDF[:-1])
    else:
        path.write_bytes(PDF[:-1] + b"X")
    with pytest.raises(ValueError, match="No intact cached original"):
        export_files(store, [item_id])


def test_selection_with_missing_file_fails_without_returning_partial_success(cached_resource):
    store, create = cached_resource
    first, _ = create()
    missing, _ = create(body=None)
    with store.connection() as db:
        before = list(db.execute("SELECT action, object_id FROM audit"))
    with pytest.raises(ValueError, match="No intact cached original"):
        export_files(store, [first, missing])
    with store.connection() as db:
        assert list(db.execute("SELECT action, object_id FROM audit")) == before


def test_export_rejects_record_pointing_outside_download_cache(cached_resource, tmp_path):
    store, create = cached_resource
    item_id, _ = create()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(PDF)
    change_download_record(store, item_id, path=str(outside))
    with pytest.raises(ValueError, match="No intact cached original"):
        export_files(store, [item_id])
    assert outside.read_bytes() == PDF


def test_export_rejects_symlinked_file_even_when_bytes_match(cached_resource, tmp_path):
    store, create = cached_resource
    item_id, record = create()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(PDF)
    link = Path(record["path"]).with_name("linked.pdf")
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"File symlink creation unavailable: {error.winerror if hasattr(error, 'winerror') else error.errno}")
    change_download_record(store, item_id, path=str(link))
    with pytest.raises(ValueError, match="No intact cached original"):
        export_files(store, [item_id])


def test_export_rejects_redirected_download_cache(cached_resource):
    store, create = cached_resource
    item_id, _ = create()
    cache = store.root / "downloads"
    retained = store.root / "retained-synthetic-downloads"
    cache.rename(retained)
    try:
        cache.symlink_to(retained, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlink creation unavailable: {error.winerror if hasattr(error, 'winerror') else error.errno}")
    with pytest.raises(ValueError, match="cache is redirected"):
        export_files(store, [item_id])


@pytest.mark.parametrize("changes", [
    {"size_bytes": len(PDF) + 1}, {"sha256": "0" * 64},
    {"filename": "../outside.pdf"}, {"filename": "invalid:name.pdf"},
])
def test_export_rejects_inconsistent_or_unsafe_cache_metadata(cached_resource, changes):
    store, create = cached_resource
    item_id, _ = create()
    change_download_record(store, item_id, **changes)
    with pytest.raises(ValueError):
        export_files(store, [item_id])


@pytest.mark.parametrize("source,kind", [("myed", "resource"), ("learn", "course")])
def test_export_requires_observed_learn_resource(cached_resource, source, kind):
    store, create = cached_resource
    item_id, _ = create(body=None, source=source, kind=kind)
    with pytest.raises(ValueError, match="observed Learn resource"):
        export_files(store, [item_id])


def test_export_rejects_duplicate_ids(cached_resource):
    store, create = cached_resource
    item_id, _ = create()
    with pytest.raises(ValueError, match="Duplicate item_ids"):
        export_files(store, [item_id, item_id])


@pytest.mark.parametrize("item_ids", [[], [f"item-{i}" for i in range(31)], "one-id", [""], [None], ["x" * 513]])
def test_invalid_batches_fail_before_cache_lookup(cached_resource, monkeypatch, item_ids):
    store, _ = cached_resource
    def unexpected(*args):
        pytest.fail("Invalid selection must be rejected before any cache lookup")
    monkeypatch.setattr(store, "item", unexpected)
    with pytest.raises(ValueError):
        export_files(store, item_ids)


@pytest.mark.parametrize("max_megabytes", [0, 33, True, 1.5, "1"])
def test_invalid_byte_limits_fail_before_cache_lookup(cached_resource, monkeypatch, max_megabytes):
    store, _ = cached_resource
    def unexpected(*args):
        pytest.fail("Invalid limits must be rejected before any cache lookup")
    monkeypatch.setattr(store, "item", unexpected)
    with pytest.raises(ValueError, match="max_megabytes"):
        export_files(store, ["item-id"], max_megabytes=max_megabytes)


def test_export_enforces_total_bytes_across_selected_files(cached_resource):
    store, create = cached_resource
    body = b"x" * (600 * 1024)
    first, _ = create(body, "first.txt")
    second, _ = create(body, "second.txt")
    with pytest.raises(ValueError, match="byte limit"):
        export_files(store, [first, second], max_megabytes=1)
    result = export_files(store, [first, second], max_megabytes=2)
    assert result.structuredContent["total_bytes"] == len(body) * 2
    assert [raw_resource(resource) for resource in resources(result)] == [body, body]


def test_zip_overhead_counts_towards_payload_limit(cached_resource):
    store, create = cached_resource
    body = random.Random(123).randbytes(1024 * 1024)
    item_id, _ = create(body, "uncompressible.txt")
    assert export_files(store, [item_id], max_megabytes=1).structuredContent["total_bytes"] == len(body)
    with pytest.raises(ValueError, match="ZIP plus manifest exceeds"):
        export_files(store, [item_id], mode="bundle", max_megabytes=1)


def test_maximum_batch_is_exportable_as_metadata(cached_resource):
    store, create = cached_resource
    item_ids = [create(filename=f"handout-{index}.pdf")[0] for index in range(30)]
    result = export_files(store, item_ids, mode="manifest")
    assert [record["item_id"] for record in result.structuredContent["files"]] == item_ids
    assert result.structuredContent["total_bytes"] == len(PDF) * 30
    assert resources(result) == []


@pytest.mark.parametrize("sensitive_key", ["token", "X-Amz-Signature"])
def test_export_rejects_signed_source_page_from_corrupt_cache(cached_resource, sensitive_key):
    store, create = cached_resource
    item_id, _ = create()
    change_download_record(
        store, item_id,
        source_page_url=f"https://www.learn.ed.ac.uk/course?{sensitive_key}=SYNTHETIC_BAD_CACHE_SECRET",
    )
    with pytest.raises(ValueError) as error:
        export_files(store, [item_id])
    assert "SYNTHETIC_BAD_CACHE_SECRET" not in str(error.value)




@pytest.fixture
def public_export_server(cached_resource, monkeypatch):
    """Load the real server with a private fixture store and isolated tool catalog."""
    import importlib.util
    import sys
    import uuid

    store, create = cached_resource

    def load(profile="full"):
        monkeypatch.setenv("UOE_TOOL_PROFILE", profile)
        monkeypatch.setenv("EDINBURGH_STUDY_HOME", str(store.root))
        monkeypatch.setenv("UOE_LOCALE", "auto")
        name = "edinburgh_study_agent._file_delivery_test_" + uuid.uuid4().hex
        source = Path(__file__).parents[1] / "src/edinburgh_study_agent/server.py"
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, "store", lambda: store)
        return module

    return load, store, create


@pytest.mark.parametrize("profile", ["full", "student", "daily"])
@pytest.mark.parametrize("mode", ["files", "manifest", "bundle"])
def test_public_mcp_export_preserves_contract_and_binary_content(public_export_server, monkeypatch, profile, mode):
    import asyncio
    from jsonschema import Draft202012Validator
    from edinburgh_study_agent import contracts
    from edinburgh_study_agent.protocol import PortableFastMCP

    load, store, create = public_export_server
    item_id, _ = create()
    server = load(profile)
    assert isinstance(server.mcp, PortableFastMCP)

    def unexpected_network_or_worker(*args, **kwargs):
        pytest.fail("Export must not refresh, download, or start a campus worker")

    monkeypatch.setattr(httpx.Client, "send", unexpected_network_or_worker)
    monkeypatch.setattr(server.school, "start_job", unexpected_network_or_worker)
    catalog = asyncio.run(server.mcp.list_tools())
    descriptor = next(tool for tool in catalog if tool.name == "study_export_files")
    Draft202012Validator.check_schema(descriptor.outputSchema)
    assert descriptor.annotations.readOnlyHint is True
    assert descriptor.annotations.destructiveHint is False
    assert descriptor.annotations.openWorldHint is False
    reply = asyncio.run(server.mcp.call_tool("study_export_files", {"item_ids": [item_id], "mode": mode}))
    assert not reply.isError, reply.structuredContent
    receipt = reply.structuredContent
    assert receipt["_contract"] == {"version": "1", "operation": "study_export_files"}
    Draft202012Validator(descriptor.outputSchema).validate(receipt)
    contracts.validate_result("study_export_files", receipt)
    text = [entry.text for entry in reply.content if entry.type == "text"]
    assert len(text) == 1
    assert json.loads(text[0]) == receipt
    assert receipt["files"][0]["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert receipt["total_bytes"] == len(PDF)
    exported = resources(reply)
    if mode == "manifest":
        assert exported == []
        assert receipt["host_registration"] == "not_requested"
    else:
        assert receipt["state"] == "awaiting_host_receipt"
        assert len(exported) == len(receipt["payloads"]) == 1
        blob = raw_resource(exported[0])
        payload = receipt["payloads"][0]
        assert len(blob) == payload["size_bytes"]
        assert hashlib.sha256(blob).hexdigest() == payload["sha256"]
        assert str(exported[0].uri) == payload["resource_uri"]
        assert exported[0].mimeType == payload["mime_type"]
        if mode == "files":
            assert blob == PDF
        else:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                assert archive.read(manifest["files"][0]["bundle_path"]) == PDF
    assert base64.b64encode(PDF).decode() not in text[0]


@pytest.mark.parametrize("damage", ["negative_size", "invalid_hash", "false_delivery_state", "missing_source"])
def test_public_mcp_rejects_invalid_export_contract_before_delivering_blobs(public_export_server, monkeypatch, damage):
    import asyncio
    from copy import deepcopy
    from jsonschema import Draft202012Validator
    from edinburgh_study_agent import contracts

    load, _, create = public_export_server
    item_id, _ = create()
    server = load()
    original = server.delivery.export_files

    def invalid_output(*args, **kwargs):
        reply = original(*args, **kwargs)
        receipt = deepcopy(reply.structuredContent)
        if damage == "negative_size":
            receipt["payloads"][0]["size_bytes"] = -1
        elif damage == "invalid_hash":
            receipt["files"][0]["sha256"] = "unverified"
        elif damage == "false_delivery_state":
            receipt["state"] = "drive_upload_verified"
        else:
            del receipt["files"][0]["source_page_url"]
        return reply.model_copy(update={"structuredContent": receipt})

    monkeypatch.setattr(server.delivery, "export_files", invalid_output)
    reply = asyncio.run(server.mcp.call_tool("study_export_files", {"item_ids": [item_id]}))
    assert reply.isError is True
    assert reply.structuredContent["error"]["operation"] == "study_export_files"
    assert reply.structuredContent["error"]["code"] == "OUTPUT_VALIDATION_ERROR"
    assert resources(reply) == []
    assert json.loads(reply.content[0].text) == reply.structuredContent
    Draft202012Validator(contracts.output_schema("study_export_files")).validate(reply.structuredContent)


def test_public_mcp_returns_safe_error_for_incomplete_export_selection(public_export_server):
    import asyncio
    from edinburgh_study_agent import contracts

    load, _, create = public_export_server
    intact, _ = create()
    missing, _ = create(body=None)
    server = load()
    reply = asyncio.run(server.mcp.call_tool("study_export_files", {"item_ids": [intact, missing]}))
    assert reply.isError is True
    assert reply.structuredContent["error"]["code"] == "INVALID_ARGUMENT"
    assert reply.structuredContent["error"]["operation"] == "study_export_files"
    assert resources(reply) == []
    assert json.loads(reply.content[0].text) == reply.structuredContent
    contracts.validate_error(reply.structuredContent)


def test_export_does_not_request_duplicate_widget_registration(public_export_server):
    import asyncio
    load, _, _ = public_export_server
    server = load("full")
    async def check():
        tool = next(t for t in await server.mcp.list_tools() if t.name == "study_export_files")
        assert not (tool.meta or {}).get("openai/outputTemplate")
        assert not (tool.meta or {}).get("ui", {}).get("resourceUri")
        html = server.study_file_receiver_compatibility()
        assert "<script" not in html.lower()
        assert "uploadFile" not in html
        assert "http" not in html
    asyncio.run(check())


def test_export_ignores_machine_specific_mime_overrides(cached_resource, monkeypatch):
    import mimetypes
    store, create = cached_resource
    body = synthetic_xlsx()
    item_id, _ = create(body, "lecture.XLSX")
    monkeypatch.setitem(mimetypes.types_map, ".xlsx", "application/octet-stream")
    result = export_files(store, [item_id])
    assert resources(result)[0].mimeType == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert raw_resource(resources(result)[0]) == body
