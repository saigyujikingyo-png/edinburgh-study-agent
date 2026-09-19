"""Regression coverage for delegated workers, login failures and refresh scope."""
from contextlib import contextmanager
from datetime import timedelta
import asyncio
import json
import runpy
import warnings

import pytest

from edinburgh_study_agent import school
from edinburgh_study_agent.models import Item, Observation, now_utc
from edinburgh_study_agent.store import Store


def course_store(tmp_path):
    store = Store(tmp_path)
    store.capture(Observation(
        source="learn", source_url=school.LEARN_HOME, title="Synthetic courses",
        observed_at=now_utc()-timedelta(days=1), scope="Synthetic test",
        authentication="authenticated", text="Chemistry\nOld notes.pdf",
        items=[Item(kind="course", native_id="_1_1", title="Chemistry", excerpt="Chemistry", status="available"),
               Item(kind="resource", native_id="_2_1", course_id="_1_1", title="Old notes.pdf",
                    excerpt="Old notes.pdf", url="https://www.learn.ed.ac.uk/ultra/courses/_1_1/file/_2_1")]))
    return store


@pytest.mark.parametrize("exception_name,expected_state,expected_code", [
    ("LoginRequired", "needs_login", "LOGIN_REQUIRED"),
    ("SchoolPageNotReady", "failed", "PAGE_NOT_READY"),
])
def test_delegated_module_errors_retain_classification(tmp_path, monkeypatch, exception_name, expected_state, expected_code):
    # The real worker is launched with -m, while workflow modules import school.
    # Load a second namespace without running its command-line main function.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        module = runpy.run_module("edinburgh_study_agent.school", run_name="__worker_fixture__")
    execute = module["execute_job"]
    namespace = execute.__globals__
    store = Store(tmp_path)
    job_id = "a"*32
    school.write_json(school.job_path(store, job_id), {
        "job_id":job_id, "action":"messages", "arguments":{}, "state":"queued",
        "created_at":now_utc().isoformat(), "updated_at":now_utc().isoformat()})
    @contextmanager
    def browser(*args, **kwargs):
        yield type("Context", (), {"pages":[object()]})()
    monkeypatch.setitem(namespace, "browser_context", browser)
    from edinburgh_study_agent import learn_updates
    def read(*args, **kwargs):
        raise getattr(school, exception_name)()
    monkeypatch.setattr(learn_updates, "read", read)
    execute(store, job_id)
    result = school.read_job(store, job_id)
    assert result["state"] == expected_state
    assert result["failure"]["code"] == expected_code
    assert "result" not in result
    assert namespace[exception_name] is getattr(school, exception_name)


def test_unscoped_refresh_returns_course_selection_without_starting_browser(tmp_path, monkeypatch):
    store = course_store(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("A scope choice must not launch a browser")
    monkeypatch.setattr(school.subprocess, "Popen", forbidden)
    value = school.start_job(store, "materials", {"operation":"list", "refresh":True})
    assert value["state"] == "partial"
    assert value["browser_started"] is False
    assert value["result"]["needs_course_selection"] is True
    assert value["result"]["remote_freshness_checked"] is False
    assert any(i["course"] == "_1_1" for i in value["result"]["courses"])


def test_material_pagination_bounds_are_in_mcp_schema():
    from edinburgh_study_agent import server
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "study_materials")
    field = tool.inputSchema["properties"]["limit"]
    # Conservative hosts receive bounds in descriptions; Pydantic enforces them.
    assert "minimum=1" in field["description"] and "maximum=30" in field["description"]
    assert "minimum=0" in tool.inputSchema["properties"]["offset"]["description"]
    result = asyncio.run(server.mcp.call_tool("study_materials", {"limit":100}))
    assert result.isError and result.structuredContent["error"]["code"] == "INVALID_ARGUMENT"


@pytest.fixture(scope="module")
def browser_page():
    import os
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("Synthetic browser tests require a non-root sandboxed runner.")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="chrome", headless=True, chromium_sandbox=True)
        yield browser
        browser.close()


def test_real_redirect_failure_reports_sso_host_without_sensitive_url(browser_page):
    from edinburgh_study_agent.school_errors import SchoolNetworkError
    page = browser_page.new_page(offline=True)
    intercepted = []
    def route_request(route):
        url = route.request.url
        intercepted.append(url)
        if url == school.LEARN_HOME:
            route.fulfill(status=200, content_type="text/html", body=(
                '<a href="/auth-saml/saml/login?SAMLRequest=PRIVATE_SENTINEL">Login to Learn</a>'))
        elif "auth-saml" in url:
            # A 302 follow-up can bypass Playwright's route handler. A script
            # handoff creates a separately intercepted top-level navigation.
            # Offline mode additionally prevents any real campus fallback.
            route.fulfill(status=200, content_type="text/html", body=(
                '<script>location.replace("https://idp.ed.ac.uk/login?SAMLRequest=PRIVATE_SENTINEL")</script>'))
        else:
            route.abort("timedout")
    page.route("**/*", route_request)
    try:
        with pytest.raises(SchoolNetworkError) as caught:
            school.goto_learn(page)
        failure = caught.value.failure
        assert failure["code"] == "NETWORK_TIMEOUT"
        assert failure["stage"] == "campus_sign_in" and failure["target_host"] == "idp.ed.ac.uk"
        assert any(url.startswith("https://idp.ed.ac.uk/") for url in intercepted)
        assert "PRIVATE_SENTINEL" not in json.dumps(failure)
        assert "SAMLRequest" not in json.dumps(failure)
    finally:
        page.close()


@pytest.mark.parametrize("status,expected,code", [
    (401, school.LoginRequired, "LOGIN_REQUIRED"),
    (503, school.SchoolNetworkError, "HTTP_ERROR"),
])
def test_http_failure_is_not_a_twenty_second_content_wait(browser_page, status, expected, code):
    page = browser_page.new_page(offline=True)
    page.route("**/*", lambda route: route.fulfill(status=status, body="Synthetic service response"))
    try:
        with pytest.raises(expected) as caught:
            school.goto_learn(page)
        assert caught.value.failure["code"] == code
        assert caught.value.failure["http_status"] == status
    finally:
        page.close()


def test_unrelated_iframe_failure_does_not_block_authenticated_content(browser_page):
    page = browser_page.new_page(offline=True)
    page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=(
        '<a id="course-link-_1_1">Synthetic course</a><iframe src="https://elsewhere.example/fail"></iframe>'))
        if route.request.url == school.LEARN_HOME else route.abort("connectionrefused"))
    try:
        school.goto_learn(page)
        assert school.authenticated(page)
    finally:
        page.close()


def test_recent_network_failure_blocks_repeated_live_reads_but_not_cache_or_other_services(tmp_path, monkeypatch):
    from edinburgh_study_agent.school_errors import diagnostic
    store = course_store(tmp_path)
    stamp = now_utc()
    job_id = "b"*32
    school.write_json(school.job_path(store,job_id), {
        "job_id":job_id,"action":"messages","state":"failed", "created_at":stamp.isoformat(),
        "updated_at":stamp.isoformat(),"failure":diagnostic("NETWORK_TIMEOUT",host="idp.ed.ac.uk",stage="campus_sign_in")})
    monkeypatch.setattr(school.subprocess, "Popen", lambda *a,**k:pytest.fail("Cooldown must not spawn"))
    first = school.start_job(store,"courses",{})
    repeat = school.start_job(store,"courses",{})
    assert first["job_id"] == repeat["job_id"] and first["blocked_by_job_id"] == job_id
    assert first["browser_started"] is False and first["action"] == "courses"
    assert first["retry_after_seconds"] <= 60
    cached = school.start_job(store,"materials",{"operation":"list"})
    assert cached["state"] == "partial" and cached["result"]["items"]
    assert school.recent_connection_failure(store,"results",{}) is None
    monkeypatch.setattr(school,"now_utc",lambda:stamp+timedelta(seconds=61))
    assert school.recent_connection_failure(store,"courses",{}) is None


def test_permission_failure_does_not_block_other_courses(tmp_path):
    from edinburgh_study_agent.school_errors import diagnostic
    store = Store(tmp_path)
    stamp = now_utc().isoformat()
    school.write_json(school.job_path(store,"c"*32), {
        "job_id":"c"*32,"action":"resources","state":"failed","updated_at":stamp,
        "failure":diagnostic("HTTP_ERROR",host="www.learn.ed.ac.uk",http_status=403)})
    assert school.recent_connection_failure(store,"courses",{}) is None
