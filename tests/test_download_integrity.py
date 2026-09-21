"""Offline source-binding and failure-meaning regressions; no campus requests."""
from contextlib import contextmanager
from html import escape
import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import pytest
from edinburgh_study_agent import school, learn_files, contracts
from edinburgh_study_agent.downloads import download_resource, list_downloads
from edinburgh_study_agent.file_errors import FileDownloadError
from edinburgh_study_agent.models import Item, Observation, now_utc
from edinburgh_study_agent.store import Store

PAGE = "https://www.learn.ed.ac.uk/ultra/courses/_1_1/file/_2_1"
ORIGINAL = "https://www.learn.ed.ac.uk/content/source.pdf?signature=synthetic"
ITEM = {"id":"synthetic", "kind":"resource", "course_id":"_1_1",
        "title":"Source.pdf", "url":PAGE}


@pytest.fixture(scope="module")
def browser():
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("Sandboxed Chrome requires a non-root runner.")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="chrome", headless=True, chromium_sandbox=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


def preview(original=ORIGINAL, name="Source.pdf", visible=True):
    return '<iframe title="'+escape(name, quote=True)+'" style="'+("" if visible else "display:none")+'" src="/viewer?originalUrl='+quote(original, safe="")+'"></iframe>'


def site(page, html):
    # Fulfil every request, including unrecognised URLs, so fixtures are offline.
    def route(route):
        body = "<button>Download</button>" if urlsplit(route.request.url).path == "/viewer" else html
        route.fulfill(status=200, content_type="text/html", body=body)
    page.route("**/*", route)
    return lambda p, url: p.goto(url, wait_until="load")


def test_hidden_previous_preview_is_never_selected_or_renamed(page):
    stale = preview("https://www.learn.ed.ac.uk/content/other.pdf", "Other.pdf", False)
    url, name, binding = learn_files.resolve_original(page, ITEM, site(page, stale+preview()))
    assert url == ORIGINAL and name == "Source.pdf"
    assert binding["content_id"] == "_2_1"
    assert binding["content_path"] == urlsplit(PAGE).path
    assert "signature" not in json.dumps(binding)


def test_same_name_visible_previews_are_ambiguous(page):
    html = preview()+preview("https://www.learn.ed.ac.uk/content/another.pdf")
    with pytest.raises(FileDownloadError) as error:
        learn_files.resolve_original(page, ITEM, site(page, html))
    assert error.value.code == "ATTACHMENT_AMBIGUOUS"
    assert error.value.candidates == ["Source.pdf", "Source.pdf"]
    assert not error.value.fields()["automatic_retry"]


@pytest.mark.parametrize("label", ["Weekly reading", "Weekly reading.pdf"])
def test_descriptive_label_uses_preview_filename_not_label(page, label):
    item = {**ITEM, "title":label}
    _, name, binding = learn_files.resolve_original(page, item, site(page, preview()))
    assert name == "Source.pdf" and "requested_filename" not in binding


def test_wrong_current_resource_page_is_rejected(page):
    navigate = site(page, preview())
    def wrong(p, url):
        navigate(p, url.replace("_2_1", "_3_1"))
    with pytest.raises(FileDownloadError) as error:
        learn_files.resolve_original(page, ITEM, wrong)
    assert error.value.code == "ATTACHMENT_MISMATCH"


@pytest.mark.parametrize("kind", ["document", "assessment"])
def test_known_page_container_fails_before_navigation(kind):
    def forbidden(*_):
        pytest.fail("A page-only entry must not trigger download navigation.")
    with pytest.raises(FileDownloadError) as error:
        learn_files.resolve_original(None, {**ITEM, "url":PAGE.replace("/file/", "/"+kind+"/")}, forbidden)
    assert error.value.code == "UNSUPPORTED_CONTAINER"
    assert error.value.recovery_action == "read_page"


def test_loading_preview_has_a_different_failure_from_container(page, monkeypatch):
    monkeypatch.setattr(learn_files, "PREVIEW_TIMEOUT", 0.01)
    with pytest.raises(FileDownloadError) as error:
        learn_files.resolve_original(page, ITEM, site(page, "<p>Loading</p>"))
    assert error.value.code == "PREVIEW_NOT_READY"


@pytest.fixture
def resource(tmp_path):
    store = Store(tmp_path/"data")
    observation = Observation(source="learn", source_url=PAGE, title="Synthetic", scope="Offline",
        observed_at=now_utc(), text="Source.pdf",
        items=[Item(native_id="_2_1", kind="resource", title="Source.pdf", excerpt="Source.pdf",
                    course_id="_1_1", url=PAGE)])
    return store, store.capture(observation)["inserted"][0]


def test_receipt_binds_source_and_never_persists_signed_address(resource):
    store, key = resource
    binding = {"method":"unique_visible_preview", "content_id":"_2_1",
               "content_path":urlsplit(PAGE).path, "preview_filename":"Source.pdf"}
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"%PDF-1.7\\nsynthetic"))) as client:
        record = download_resource(store, key, ORIGINAL, "Source.pdf", client=client, binding=binding)
    assert record["attachment_binding"] == binding
    value = list_downloads(store)
    contracts.validate_result("study_downloads", {**value, "_contract":{"version":"1","operation":"study_downloads"}})
    with store.connection() as db:
        assert "signature" not in "\\n".join(db.iterdump())
    assert Path(record["path"]).exists()


def test_header_supplies_filename_without_preview_name(resource):
    store, key = resource
    binding = {"method":"unique_visible_preview", "content_id":"_2_1",
               "content_path":urlsplit(PAGE).path}
    def respond(_):
        return httpx.Response(200, content=b"%PDF-1.7\\nfixture",
                              headers={"Content-Disposition":'attachment; filename="Other.pdf"'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        record = download_resource(store, key, ORIGINAL, None, client=client, binding=binding)
    assert record["filename"] == "Other.pdf" and record["title"] == "Source.pdf"
    assert record["attachment_binding"] == binding
    assert list_downloads(store)["files"][0]["filename"] == "Other.pdf"


@pytest.mark.parametrize("case,code", [
    ("http", "DOWNLOAD_HTTP_ERROR"), ("network", "DOWNLOAD_NETWORK_ERROR"),
    ("invalid_file", "FILE_VERIFICATION_FAILED"), ("container", "UNSUPPORTED_CONTAINER"),
])
def test_download_batch_preserves_distinct_safe_failures(resource, monkeypatch, case, code):
    store, key = resource
    binding = {"method":"unique_visible_preview", "content_id":"_2_1", "content_path":urlsplit(PAGE).path}
    if case == "container":
        def resolve(*_): raise FileDownloadError("UNSUPPORTED_CONTAINER")
    else:
        def resolve(*_): return ORIGINAL, "Source.pdf", binding
    monkeypatch.setattr(school, "original_file", resolve)
    def respond(request):
        if case == "network": raise httpx.ConnectError("secret "+ORIGINAL)
        return httpx.Response(503 if case == "http" else 200, content=b"<html>not a PDF</html>")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(school, "download_resource",
                            lambda *a, **kw: download_resource(*a, **kw, client=client))
        result = school.download_items(store, None, {"item_ids":[key],"refresh":True}, lambda _:None)
    failure = result["failed"][0]
    assert failure["code"] == code and not failure["automatic_retry"]
    assert not result["saved"] and not result["complete"]
    assert "signature" not in json.dumps(failure) and "secret" not in json.dumps(failure)
    contracts._check(contracts._job_validator("download"), result)
    if case == "http": assert failure["http_status"] == 503
    if case == "container": assert failure["recovery_action"] == "read_page"


def test_header_disagreeing_with_visible_preview_is_rejected(resource):
    store, key = resource
    binding = {"method":"unique_visible_preview", "content_id":"_2_1",
               "content_path":urlsplit(PAGE).path, "preview_filename":"Source.pdf"}
    def respond(_):
        return httpx.Response(200, content=b"%PDF-1.7",
                              headers={"Content-Disposition":'attachment; filename="Different.pdf"'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(FileDownloadError) as error:
            download_resource(store,key,ORIGINAL,"Source.pdf",client=client,binding=binding)
    assert error.value.code == "ATTACHMENT_MISMATCH" and not list_downloads(store)["files"]


def test_file_read_worker_retains_typed_failure(resource, monkeypatch):
    store, key = resource
    job = "a"*32
    school.write_json(school.job_path(store,job), {
        "job_id":job, "action":"read_resource", "arguments":{"item_id":key},
        "state":"queued", "created_at":now_utc().isoformat(), "updated_at":now_utc().isoformat()})
    @contextmanager
    def context(*a,**k):
        class FakeContext:
            pages=[object()]
        yield FakeContext()
    monkeypatch.setattr(school,"browser_context",context)
    def fail(*_): raise FileDownloadError("ATTACHMENT_AMBIGUOUS",candidates=["One.pdf","Two.pdf"])
    monkeypatch.setattr(school,"read_resource",fail)
    school.execute_job(store,job)
    result=school.read_job(store,job)
    assert result["state"] == "failed"
    assert result["file_failure"]["code"] == "ATTACHMENT_AMBIGUOUS"
    assert result["file_failure"]["candidates"] == ["One.pdf","Two.pdf"]
    contracts.validate_result("study_school_job",
        {**result,"_contract":{"version":"1","operation":"study_school_job"}})
