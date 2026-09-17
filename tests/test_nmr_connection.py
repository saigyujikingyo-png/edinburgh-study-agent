"""Saved setup, real browser form submission and host-native sample questions."""
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import pytest

from edinburgh_study_agent import nmr, nmr_auth, nmr_input, contracts
from edinburgh_study_agent.store import Store

PASSWORD = "synthetic-connection-only"


def saved():
    return {"provider": "legacy", "group": "3OR", "password": PASSWORD,
            "remembered": True, "expires_at": None, "insecure_http_approved": True}


@pytest.fixture(autouse=True)
def cleanup():
    yield
    for panel in list(nmr_auth._PANELS.values()):
        panel.stop.set()
        panel.thread.join(2)
    nmr_auth._MEMORY.clear()


def validate(value):
    contracts.validate_result("study_nmr", {**value, "_contract": {"version": "1", "operation": "study_nmr"}})
    return value


def get_form(client, panel):
    page = client.get(panel["url"])
    assert page.status_code == 200
    nonce = re.search(r'name="nonce" value="([A-Za-z0-9_-]+)"', page.text).group(1)
    return {"nonce": nonce, "password": PASSWORD, "http_consent": "yes", "remember": "yes"}


def test_remembered_group_survives_time_and_remains_separate(tmp_path, monkeypatch):
    receipt = nmr_auth.save_session(tmp_path, "legacy", saved(), "3OR")
    assert receipt["remembered"] and receipt["expires_at"] is None
    future = time.time() + 400 * 86400
    monkeypatch.setattr(nmr_auth.time, "time", lambda: future)
    session = nmr_auth.get_session(tmp_path, "legacy", "3OR")
    assert session["password"] == PASSWORD and session["expires_at"] == future + 3600
    assert nmr_auth.get_session(tmp_path, "legacy", "2OR") is None
    assert nmr_auth.get_session(tmp_path, "nomad") is None
    nmr_auth.forget_session(tmp_path, "legacy", "3OR")
    assert nmr_auth.get_session(tmp_path, "legacy", "3OR") is None


@pytest.mark.skipif(os.name != "nt", reason="Current-user Windows DPAPI restart acceptance")
def test_remembered_connection_survives_process_restart_encrypted(tmp_path):
    nmr_auth.save_session(tmp_path, "legacy", saved(), "3OR")
    vault = next(tmp_path.rglob("*.dpapi"))
    assert PASSWORD.encode() not in vault.read_bytes()
    code = ("import json,sys; from pathlib import Path; from edinburgh_study_agent.nmr_auth import get_session; "
            "s=get_session(Path(sys.argv[1]),'legacy','3OR'); "
            "print(json.dumps({'remembered':s['remembered'],'available':bool(s['password'])}))")
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {"remembered": True, "available": True}
    assert PASSWORD not in result.stdout + result.stderr


@pytest.mark.parametrize("changes", [{"insecure_http_approved": False}, {"remembered": "yes"}, {"group": "2OR"}])
def test_persistent_connection_cannot_expand_credential_scope(tmp_path, changes):
    with pytest.raises(ValueError, match="NMR_AUTH_INVALID_SESSION"):
        nmr_auth.save_session(tmp_path, "legacy", {**saved(), **changes}, "3OR")


def test_saved_connection_selects_group_without_panel_and_asks_only_sample(tmp_path, monkeypatch):
    store = Store(tmp_path)
    nmr_auth.save_session(tmp_path, "legacy", saved(), "3OR")
    monkeypatch.setattr(nmr_auth, "open_panel", lambda *a, **k: pytest.fail("Saved setup must not create a form"))
    connected = validate(nmr.run(store, "connect"))
    assert connected["state"] == "connected" and connected["connections"][0]["group"] == "3OR"
    missing = validate(nmr.run(store, "download"))
    assert missing["needed"] == ["sample"] and missing["provider"] == "legacy"
    seen = []

    class Legacy:
        def __init__(self, session, **kwargs):
            assert session["group"] == "3OR" and kwargs["allow_insecure_http"] is True
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def search(self, sample, **kwargs):
            seen.append(sample)
            return []

    monkeypatch.setattr(nmr, "LegacyClient", Legacy)
    completed = validate(nmr.run(store, "resume", request_id=missing["request_id"], sample="0042"))
    assert completed["state"] == "no_matches" and seen == ["0042"]
    assert nmr._request(store, missing["request_id"])["intent"] == "download"
    # A different sample is a normal new request, not repeated connection setup.
    assert nmr.run(store, "find", sample="0043")["state"] == "no_matches"
    assert seen == ["0042", "0043"]


def test_multiple_saved_groups_require_choice_and_never_try_them_all(tmp_path):
    store = Store(tmp_path)
    for group in ("3OR", "2OR"):
        nmr_auth.save_session(tmp_path, "legacy", {**saved(), "group": group}, group)
    value = validate(nmr.run(store, "find", provider="legacy", sample="0042"))
    assert value["state"] == "needs_input" and value["needed"] == ["group"]


def test_panel_post_fallback_requires_exact_referrer_cookie_and_nonce(tmp_path):
    panel = nmr_auth.open_panel(tmp_path, "legacy", "3OR", "synthetic-request")
    with httpx.Client(trust_env=False) as client:
        fields = get_form(client, panel)
        bad = client.post(panel["url"], data=fields, headers={"Origin": "null"})
        assert bad.status_code == 403
        wrong = client.post(panel["url"], data={**fields, "nonce": "wrong"}, headers={"Referer": panel["url"]})
        assert wrong.status_code == 403
        assert nmr_auth.get_session(tmp_path, "legacy", "3OR") is None
        good = client.post(panel["url"], data=fields, headers={"Origin": "null", "Referer": panel["url"], "Sec-Fetch-Site": "same-origin"})
        assert good.status_code == 200
        assert nmr_auth.get_session(tmp_path, "legacy", "3OR")["remembered"]


def test_cookie_and_http_permission_are_required_even_with_known_nonce(tmp_path):
    panel = nmr_auth.open_panel(tmp_path, "legacy", "3OR", "synthetic-request", True)
    origin = panel["url"].rsplit("/", 2)[0]
    with httpx.Client(trust_env=False) as client:
        fields = get_form(client, panel)
        missing_consent = {k: v for k, v in fields.items() if k != "http_consent"}
        assert client.post(panel["url"], data=missing_consent, headers={"Origin": origin}).status_code == 400
        assert client.post(panel["url"], data=fields, headers={"Origin": origin, "Sec-Fetch-Site": "cross-site"}).status_code == 403
        client.cookies.clear()
        assert client.post(panel["url"], data=fields, headers={"Origin": origin}).status_code == 403
    assert nmr_auth.get_session(tmp_path, "legacy", "3OR") is None


def test_rejected_panel_is_rotated_and_explicit_reconnect_invalidates_old(tmp_path):
    first = nmr_auth.open_panel(tmp_path, "legacy", "3OR", "synthetic-request")
    with httpx.Client(trust_env=False) as client:
        client.post(first["url"], data={"wrong": "request"})
        second = nmr_auth.open_panel(tmp_path, "legacy", "3OR", "synthetic-request")
        third = nmr_auth.open_panel(tmp_path, "legacy", "3OR", "synthetic-request", renew=True)
        assert len({first["connection_id"], second["connection_id"], third["connection_id"]}) == 3
        for old in (first, second):
            try:
                assert client.get(old["url"]).status_code == 410
            except httpx.TransportError:
                pass


@pytest.fixture
def browser():
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("Sandboxed browser requires a non-root runner")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="chrome", headless=True, chromium_sandbox=True)
        yield browser
        browser.close()


@pytest.mark.parametrize("locale,width", [("en-GB", 1280), ("zh-CN", 375)])
def test_real_browser_normal_form_post_and_layout(browser, tmp_path, locale, width):
    panel = nmr_auth.open_panel(tmp_path, "legacy", "3OR", "synthetic-browser")
    origin = panel["url"].rsplit("/", 2)[0]
    with browser.new_context(locale=locale, viewport={"width": width, "height": 850}) as context:
        # Only this synthetic loopback form is reachable; no school/network data.
        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(origin + "/") else route.abort())
        page = context.new_page()
        page.goto(panel["url"])
        assert page.locator("html").get_attribute("lang") == locale[:2]
        assert page.locator("body").evaluate("e => e.scrollWidth <= window.innerWidth")
        page.locator('[name="password"]').fill(PASSWORD)
        page.locator('[name="http_consent"]').check()
        if os.name == "nt":
            assert page.locator('[name="remember"]').is_checked()
        with page.expect_response(lambda response: response.request.method == "POST") as response:
            page.locator('[name="password"]').press("Enter")
        assert response.value.status == 200
        assert response.value.request.headers["origin"] == origin
        assert page.locator("input").count() == 0
        assert PASSWORD not in page.content()
    assert nmr_auth.get_session(tmp_path, "legacy", "3OR") is not None


@pytest.mark.parametrize("host_form", [True, False])
def test_host_sample_form_or_chat_fallback_keeps_zeroes(tmp_path, monkeypatch, host_form):
    store = Store(tmp_path)
    calls = []
    def backend(store, action, **kwargs):
        calls.append((action, kwargs))
        if len(calls) == 1:
            return {"state": "needs_input", "provider": "legacy", "request_id": "retained", "needed": ["sample"], "message": "Ask for sample"}
        assert action == "resume" and kwargs["sample"] == "0042" and kwargs["request_id"] == "retained"
        return {"state": "no_matches", "provider": "legacy", "request_id": "retained", "message": "No matches"}
    monkeypatch.setattr(nmr, "run", backend)
    class Host:
        session = SimpleNamespace(client_params=SimpleNamespace(capabilities=SimpleNamespace(elicitation=SimpleNamespace(form={} if host_form else None))))
        async def elicit(self, message, schema):
            assert list(schema.model_fields) == ["sample"]
            return SimpleNamespace(action="accept", data=schema(sample="0042"))
    value = asyncio.run(nmr_input.interact(store, "download", ctx=Host()))
    assert value["state"] == ("no_matches" if host_form else "needs_input")
    assert len(calls) == (2 if host_form else 1)
    assert nmr_input.input_model(["password"]) is None
    assert nmr_input.input_model(["sample", "token"]) is None
