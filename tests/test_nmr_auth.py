"""Synthetic vault and real-loopback checks; no campus credentials or traffic."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import threading
import time
from urllib.parse import urlsplit

import httpx
import pytest

from edinburgh_study_agent import nmr_auth


TOKEN = "synthetic_header.synthetic_payload.synthetic_signature"
PASSWORD = "Synthetic-only<&>password"


def nomad_session():
    return {"provider": "nomad", "token": TOKEN, "user_id": "a" * 24,
            "username": "synthetic-student", "group": "Synthetic group",
            "expires_at": time.time() + 600}


def legacy_session(group="3OR"):
    return {"provider": "legacy", "group": group, "password": PASSWORD,
            "expires_at": time.time() + 1800, "insecure_http_approved": True}


@pytest.fixture(autouse=True)
def close_synthetic_panels():
    yield
    for panel in list(nmr_auth._PANELS.values()):
        panel.stop.set()
        panel.thread.join(timeout=2)
    nmr_auth._MEMORY.clear()


@contextmanager
def client():
    with httpx.Client(trust_env=False, timeout=3, follow_redirects=False) as connection:
        yield connection


def form(connection, panel):
    response = connection.get(panel["url"])
    assert response.status_code == 200
    match = re.search(r'name="nonce" value="([A-Za-z0-9_-]+)"', response.text)
    assert match
    return response, {"nonce": match.group(1), **({"http_consent": "yes"} if 'name="http_consent"' in response.text else {})}


def origin(panel):
    parsed = urlsplit(panel["url"])
    return f"{parsed.scheme}://{parsed.netloc}"


def post(connection, panel, data, **headers):
    return connection.post(panel["url"], data=data, headers={"Origin": origin(panel), **headers})


def test_memory_fallback_does_not_create_plaintext_files(tmp_path, monkeypatch):
    monkeypatch.setattr(nmr_auth, "_WINDOWS", False)
    root = tmp_path / "private"
    assert nmr_auth.get_session(root, "nomad") is None
    receipt = nmr_auth.save_session(root, "nomad", nomad_session())
    assert receipt["persistence"] == "process_memory_only"
    assert receipt["authentication"] == "authenticated"
    assert TOKEN not in json.dumps(receipt)
    session = nmr_auth.get_session(root, "nomad")
    assert session["token"] == TOKEN
    assert session["persistence"] == "process_memory_only"
    session["token"] = "changed-by-caller"
    assert nmr_auth.get_session(root, "nomad")["token"] == TOKEN
    assert not root.exists()
    nmr_auth.forget_session(root, "nomad")
    assert nmr_auth.get_session(root, "nomad") is None


@pytest.mark.skipif(os.name != "nt", reason="Current-user Windows DPAPI check")
def test_windows_vault_is_encrypted_atomic_and_readable_by_current_user(tmp_path):
    root = tmp_path / "private"
    receipt = nmr_auth.save_session(root, "nomad", nomad_session())
    assert receipt["persistence"] == "windows_dpapi"
    files = list(root.rglob("*"))
    vaults = [path for path in files if path.is_file()]
    assert len(vaults) == 1
    assert vaults[0].suffix == ".dpapi"
    encrypted = vaults[0].read_bytes()
    assert TOKEN.encode() not in encrypted
    assert b"synthetic-student" not in encrypted
    assert nmr_auth.get_session(root, "nomad")["token"] == TOKEN
    updated = nomad_session()
    updated["username"] = "second-synthetic-student"
    nmr_auth.save_session(root, "nomad", updated)
    assert nmr_auth.get_session(root, "nomad")["username"] == updated["username"]
    assert len([path for path in root.rglob("*") if path.is_file()]) == 1
    nmr_auth.forget_session(root, "nomad")
    assert nmr_auth.get_session(root, "nomad") is None


@pytest.mark.skipif(os.name != "nt", reason="Current-user Windows DPAPI check")
def test_tampered_or_oversized_vault_errors_are_bounded_and_redacted(tmp_path):
    root = tmp_path / "private"
    nmr_auth.save_session(root, "nomad", nomad_session())
    vault = next(root.rglob("*.dpapi"))
    vault.write_bytes(b"SYNTHETIC SECRET INVALID CIPHERTEXT")
    with pytest.raises(ValueError, match="^NMR_AUTH_INVALID_VAULT$"):
        nmr_auth.get_session(root, "nomad")
    vault.write_bytes(b"x" * (nmr_auth.MAX_VAULT_BYTES + 1))
    with pytest.raises(ValueError, match="^NMR_AUTH_INVALID_VAULT$"):
        nmr_auth.get_session(root, "nomad")


@pytest.mark.skipif(os.name != "nt", reason="Current-user Windows DPAPI check")
def test_failed_atomic_replacement_preserves_the_previous_session(tmp_path, monkeypatch):
    root = tmp_path / "private"
    nmr_auth.save_session(root, "nomad", nomad_session())
    previous = next(root.rglob("*.dpapi")).read_bytes()

    def fail_replace(*_):
        raise OSError("SYNTHETIC PRIVATE FILESYSTEM ERROR")

    monkeypatch.setattr(nmr_auth.os, "replace", fail_replace)
    changed = {**nomad_session(), "username": "replacement-account"}
    with pytest.raises(ValueError, match="^NMR_AUTH_STORAGE_UNAVAILABLE$"):
        nmr_auth.save_session(root, "nomad", changed)
    assert next(root.rglob("*.dpapi")).read_bytes() == previous
    assert nmr_auth.get_session(root, "nomad")["username"] == "synthetic-student"
    assert not list(root.rglob("*.tmp"))


@pytest.mark.parametrize("provider,group", [
    ("arbitrary", None), ("nomad", "3OR"), ("legacy", None),
    ("legacy", "*"), ("legacy", "../../secret"), ("legacy", "arbitrary"),
])
def test_provider_and_group_allowlist_is_checked_before_storage(tmp_path, provider, group):
    for action in (
        lambda: nmr_auth.get_session(tmp_path, provider, group),
        lambda: nmr_auth.save_session(tmp_path, provider, {}, group),
        lambda: nmr_auth.forget_session(tmp_path, provider, group),
        lambda: nmr_auth.open_panel(tmp_path, provider, group, "request-1"),
    ):
        with pytest.raises(ValueError, match="^NMR_AUTH_INVALID_PROVIDER_OR_GROUP$"):
            action()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("changes", [
    {"token": "x" * 20000}, {"token": "a.b.c\r\nsecret"}, {"user_id": "other"},
    {"provider": "legacy"}, {"expires_at": float("inf")}, {"expires_at": True},
    {"expires_at": 10 ** 1000},
    {"expires_at": time.time() - 3600}, {"password": PASSWORD},
    {"unexpected": {"private": PASSWORD}}, {"username": "\x00private"},
])
def test_saved_nomad_session_is_bounded_and_strict(tmp_path, changes):
    with pytest.raises(ValueError, match="^NMR_AUTH_INVALID_SESSION$"):
        nmr_auth.save_session(tmp_path, "nomad", {**nomad_session(), **changes})


def test_legacy_session_requires_approval_and_has_unverified_one_hour_lifetime(tmp_path, monkeypatch):
    monkeypatch.setattr(nmr_auth, "_WINDOWS", False)
    value = legacy_session()
    value.pop("insecure_http_approved")
    with pytest.raises(ValueError, match="^NMR_AUTH_INVALID_SESSION$"):
        nmr_auth.save_session(tmp_path, "legacy", value, "3OR")
    value = legacy_session()
    value["expires_at"] = time.time() + 7200
    with pytest.raises(ValueError, match="^NMR_AUTH_INVALID_SESSION$"):
        nmr_auth.save_session(tmp_path, "legacy", value, "3OR")
    receipt = nmr_auth.save_session(tmp_path, "legacy", legacy_session(), "3OR")
    assert receipt["authentication"] == "credentials_supplied"
    assert nmr_auth.get_session(tmp_path, "legacy", "3OR")["password"] == PASSWORD
    assert nmr_auth.get_session(tmp_path, "legacy", "2OR") is None


def test_expired_memory_session_is_not_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(nmr_auth, "_WINDOWS", False)
    now = time.time()
    nmr_auth.save_session(tmp_path, "nomad", {**nomad_session(), "expires_at": now + 1})
    monkeypatch.setattr(nmr_auth.time, "time", lambda: now + 2)
    assert nmr_auth.get_session(tmp_path, "nomad") is None


def test_nomad_panel_logs_in_directly_without_returning_secrets(tmp_path, monkeypatch, capsys):
    calls = []

    class FakeNomad:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def login(self, username, password):
            calls.append((username, password))
            return nomad_session()

    monkeypatch.setattr(nmr_auth, "NomadClient", FakeNomad)
    panel = nmr_auth.open_panel(tmp_path, "nomad", None, "pending-sample-42")
    assert set(panel) == {"url", "connection_id", "expires_at", "reachability"}
    assert panel["reachability"] == "runtime_computer_browser"
    with client() as connection:
        response, data = form(connection, panel)
        assert "NOMAD username" in response.text
        assert "<script" not in response.text.lower()
        assert 'type="password"' in response.text
        assert 'form-action \'self\'' in response.headers["Content-Security-Policy"]
        assert response.headers["Cache-Control"].startswith("no-store")
        assert response.headers["Referrer-Policy"] == "same-origin"
        assert response.headers["X-Frame-Options"] == "DENY"
        data.update(username="synthetic-student", password=PASSWORD)
        completed = post(connection, panel, data)
        assert completed.status_code == 200
        assert "Return to your agent" in completed.text
        assert "session is reused" in completed.text
        assert PASSWORD not in completed.text and TOKEN not in completed.text
    assert calls == [("synthetic-student", PASSWORD)]
    assert nmr_auth.get_session(tmp_path, "nomad")["token"] == TOKEN
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


def test_legacy_panel_does_not_connect_before_or_after_collecting_password(tmp_path, monkeypatch):
    monkeypatch.setattr(nmr_auth, "NomadClient", lambda: pytest.fail("Legacy must not use NOMAD login"))
    panel = nmr_auth.open_panel(tmp_path, "legacy", "3OR", "request-1")
    with client() as connection:
        response, data = form(connection, panel)
        assert "3OR" in response.text and "unencrypted HTTP" in response.text
        assert 'name="username"' not in response.text
        completed = post(connection, panel, {**data, "password": PASSWORD})
        assert completed.status_code == 200
        assert "not yet verified" in completed.text
    session = nmr_auth.get_session(tmp_path, "legacy", "3OR")
    assert session["authentication"] == "credentials_supplied"
    assert 0 < session["expires_at"] - time.time() <= 3600


@pytest.mark.parametrize("headers", [
    {"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Origin": "null"},
])
def test_panel_rejects_foreign_host_and_origin(tmp_path, headers):
    panel = nmr_auth.open_panel(tmp_path, "nomad", None, "request-1")
    with client() as connection:
        _, data = form(connection, panel)
        result = post(connection, panel, {**data, "username": "synthetic", "password": PASSWORD}, **headers)
        assert result.status_code == 403
        assert PASSWORD not in result.text
    assert nmr_auth.get_session(tmp_path, "nomad") is None


def test_missing_origin_and_wrong_nonce_are_rejected(tmp_path):
    panel = nmr_auth.open_panel(tmp_path, "nomad", None, "request-1")
    with client() as connection:
        _, data = form(connection, panel)
        data.update(username="synthetic", password=PASSWORD)
        assert connection.post(panel["url"], data=data).status_code == 403
        assert post(connection, panel, {**data, "nonce": "wrong"}).status_code == 403
        assert connection.get(panel["url"] + "unknown").status_code == 403
    assert nmr_auth.get_session(tmp_path, "nomad") is None


def test_post_size_type_and_fields_are_bounded(tmp_path):
    panel = nmr_auth.open_panel(tmp_path, "nomad", None, "request-1")
    with client() as connection:
        _, data = form(connection, panel)
        assert connection.post(panel["url"], content=b"x" * 20000,
                               headers={"Origin": origin(panel), "Content-Type": "application/x-www-form-urlencoded"}).status_code == 413
        assert connection.post(panel["url"], json=data, headers={"Origin": origin(panel)}).status_code == 415
        assert post(connection, panel, {**data, "username": "synthetic", "password": PASSWORD,
                                       "redirect": "https://evil.example"}).status_code == 400
    assert nmr_auth.get_session(tmp_path, "nomad") is None


def test_failed_login_keeps_request_and_sanitizes_error(tmp_path, monkeypatch):
    class FailingNomad:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def login(self, username, password):
            raise RuntimeError(f"PRIVATE {password} TOKEN {TOKEN} C:/private/user")

    monkeypatch.setattr(nmr_auth, "NomadClient", FailingNomad)
    panel = nmr_auth.open_panel(tmp_path, "nomad", None, "retained-request")
    with client() as connection:
        _, data = form(connection, panel)
        result = post(connection, panel, {**data, "username": "synthetic", "password": PASSWORD})
        assert result.status_code == 401
        assert "Your request is retained" in result.text
        assert PASSWORD not in result.text and TOKEN not in result.text and "C:/private" not in result.text
        assert connection.get(panel["url"]).status_code == 200
    assert nmr_auth.get_session(tmp_path, "nomad") is None


def test_expired_panel_closes_listener_and_deduplicates_pending_request(tmp_path, monkeypatch):
    monkeypatch.setattr(nmr_auth, "PANEL_TTL_SECONDS", 0.2)
    first = nmr_auth.open_panel(tmp_path, "nomad", None, "request-1")
    assert nmr_auth.open_panel(tmp_path, "nomad", None, "request-1") == first
    state = next(iter(nmr_auth._PANELS.values()))
    state.thread.join(timeout=2)
    assert not state.thread.is_alive()
    assert not nmr_auth._PANELS
    with client() as connection, pytest.raises(httpx.ConnectError):
        connection.get(first["url"])


def test_panel_request_id_is_validated_and_count_is_bounded(tmp_path):
    with pytest.raises(ValueError, match="^NMR_AUTH_INVALID_REQUEST$"):
        nmr_auth.open_panel(tmp_path, "nomad", None, '<script>alert("bad")</script>')
    for index in range(nmr_auth.MAX_PANELS):
        nmr_auth.open_panel(tmp_path, "nomad", None, f"request-{index}")
    with pytest.raises(ValueError, match="^NMR_AUTH_PANEL_LIMIT$"):
        nmr_auth.open_panel(tmp_path, "nomad", None, "request-extra")


def test_forget_invalidates_matching_panels_before_late_submission(tmp_path, monkeypatch):
    monkeypatch.setattr(nmr_auth, "_WINDOWS", False)
    panels = [nmr_auth.open_panel(tmp_path, "legacy", "3OR", f"request-{i}", allow_insecure_http=True)
              for i in range(2)]
    other = nmr_auth.open_panel(tmp_path, "legacy", "2OR", "other-group", allow_insecure_http=True)
    with client() as connection:
        forms = [form(connection, panel)[1] for panel in panels]
        nmr_auth.forget_session(tmp_path, "legacy", "3OR")
        for panel, fields in zip(panels, forms):
            try:
                response = post(connection, panel, {**fields, "password": PASSWORD})
            except httpx.TransportError:
                pass  # A closed listener also rejects an obsolete capability.
            else:
                assert response.status_code == 410
        assert connection.get(other["url"]).status_code == 200
    assert nmr_auth.get_session(tmp_path, "legacy", "3OR") is None


def test_forget_cancels_in_flight_nomad_login_before_it_can_save(tmp_path, monkeypatch):
    monkeypatch.setattr(nmr_auth, "_WINDOWS", False)
    entered, release = threading.Event(), threading.Event()

    class WaitingNomad:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def login(self, *_):
            entered.set()
            assert release.wait(3)
            return nomad_session()

    monkeypatch.setattr(nmr_auth, "NomadClient", WaitingNomad)
    panel = nmr_auth.open_panel(tmp_path, "nomad", None, "in-flight-request")
    with client() as connection, ThreadPoolExecutor(max_workers=1) as pool:
        _, fields = form(connection, panel)
        pending = pool.submit(post, connection, panel, {**fields, "username": "synthetic", "password": PASSWORD})
        try:
            assert entered.wait(2)
            nmr_auth.forget_session(tmp_path, "nomad")
        finally:
            release.set()
        assert pending.result(timeout=3).status_code == 410
    assert nmr_auth.get_session(tmp_path, "nomad") is None


def test_disconnect_is_atomic_with_panel_validation_and_save(tmp_path, monkeypatch):
    monkeypatch.setattr(nmr_auth, "_WINDOWS", False)
    save_entered, release_save = threading.Event(), threading.Event()
    disconnect_started, disconnect_finished = threading.Event(), threading.Event()
    original_save = nmr_auth.save_session

    def delayed_save(*args, **kwargs):
        save_entered.set()
        assert release_save.wait(3)
        return original_save(*args, **kwargs)

    def disconnect():
        disconnect_started.set()
        nmr_auth.forget_session(tmp_path, "legacy", "3OR")
        disconnect_finished.set()

    monkeypatch.setattr(nmr_auth, "save_session", delayed_save)
    panel = nmr_auth.open_panel(tmp_path, "legacy", "3OR", "race-request", allow_insecure_http=True)
    with client() as connection, ThreadPoolExecutor(max_workers=2) as pool:
        _, fields = form(connection, panel)
        pending = pool.submit(post, connection, panel, {**fields, "password": PASSWORD})
        try:
            assert save_entered.wait(2)
            forgotten = pool.submit(disconnect)
            assert disconnect_started.wait(2)
            completed_before_save = disconnect_finished.wait(0.15)
        finally:
            release_save.set()
        pending.result(timeout=3)
        forgotten.result(timeout=3)
    assert not completed_before_save
    assert nmr_auth.get_session(tmp_path, "legacy", "3OR") is None
