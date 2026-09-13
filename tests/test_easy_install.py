import json
from pathlib import Path
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from edinburgh_study_agent import __version__, setup_core, setup_ui


def bundle(tmp_path):
    folder = tmp_path / "installer payload"
    python = folder / "runtime/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"synthetic runtime for transactional tests")
    files = {"runtime/Scripts/python.exe": setup_core.digest(python)}
    (folder / "manifest.json").write_text(json.dumps({"product": "uoe-companion", "version": __version__, "files": files}))
    return folder


def doctor(*args):
    return {"version": __version__, "tools": 13, "stdio_initialize_list_call": "passed"}


def test_new_install_repeat_and_upgrade_preserve_private_data(tmp_path):
    payload = bundle(tmp_path)
    home = tmp_path / "private 学生 data"
    home.mkdir()
    (home / "study.sqlite3").write_bytes(b"private sentinel")
    (home / "school/profile").mkdir(parents=True)
    (home / "school/profile/session").write_bytes(b"private session sentinel")
    host = tmp_path / "host configuration.json"
    host.write_text(json.dumps({"mcpServers": {"other": {"command": "existing"}}, "theme": "dark"}))
    first = setup_core.install(payload, home, ["workbuddy"], config_paths={"workbuddy": host}, doctor=doctor)
    assert first["check"]["tools"] == 13 and not first["unchanged_runtime"]
    installed = home / "runtime/Scripts/python.exe"
    stamp = installed.stat().st_mtime_ns
    configured = host.read_bytes()
    again = setup_core.install(payload, home, ["workbuddy"], config_paths={"workbuddy": host}, doctor=doctor)
    assert again["unchanged_runtime"] and installed.stat().st_mtime_ns == stamp
    assert host.read_bytes() == configured
    assert json.loads(configured)["mcpServers"]["other"] == {"command": "existing"}
    assert json.loads(configured)["mcpServers"]["uoe-companion"]["env"]["UOE_TOOL_PROFILE"] == "daily"
    assert (home / "study.sqlite3").read_bytes() == b"private sentinel"
    assert (home / "school/profile/session").read_bytes() == b"private session sentinel"


def test_tampering_and_manifest_traversal_do_not_replace_existing_runtime(tmp_path):
    payload = bundle(tmp_path)
    home = tmp_path / "private"
    old = home / "runtime/Scripts/python.exe"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"previous runtime")
    (payload / "runtime/Scripts/python.exe").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        setup_core.install(payload, home, doctor=doctor)
    assert old.read_bytes() == b"previous runtime"
    manifest = {"product": "uoe-companion", "version": __version__, "files": {"runtime/../../outside": "0" * 64}}
    (payload / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest path"):
        setup_core.read_manifest(payload)


def test_failed_check_and_late_host_conflict_roll_back_runtime_and_configs(tmp_path):
    payload = bundle(tmp_path)
    home = tmp_path / "private"
    old = home / "runtime/Scripts/python.exe"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"working previous version")
    def fail(*args):
        raise ValueError("synthetic failed protocol check")
    with pytest.raises(ValueError, match="protocol"):
        setup_core.install(payload, home, doctor=fail)
    assert old.read_bytes() == b"working previous version"
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_text('{"mcpServers":{},"preserve":true}')
    second.write_text('{"mcpServers":{"uoe-companion":{"command":"unrelated"}}}')
    before = first.read_bytes()
    with pytest.raises(ValueError, match="unrelated"):
        setup_core.install(payload, home, ["workbuddy", "claude-desktop"],
                           config_paths={"workbuddy": first, "claude-desktop": second}, doctor=doctor)
    assert first.read_bytes() == before
    assert old.read_bytes() == b"working previous version"
    assert not list(home.glob(".setup-stage-*"))


def test_busy_runtime_and_simultaneous_install_are_not_interrupted(tmp_path, monkeypatch):
    payload = bundle(tmp_path)
    home = tmp_path / "private"
    home.mkdir()
    monkeypatch.setattr(setup_core, "runtime_processes", lambda path: [123])
    with pytest.raises(ValueError, match="in use"):
        setup_core.install(payload, home, doctor=doctor)
    with setup_core.installation_lock(home):
        with pytest.raises(ValueError, match="Another"):
            with setup_core.installation_lock(home):
                pass


def test_cleanup_guard_rejects_private_data_directory(tmp_path):
    with pytest.raises(ValueError, match="unexpected"):
        setup_core.remove_owned_stage(tmp_path / "school", tmp_path)


def test_wizard_rejects_foreign_origins_wrong_tokens_and_large_requests(tmp_path):
    wizard = setup_ui.Wizard(bundle(tmp_path), tmp_path / "private")
    server = setup_ui.make_server(wizard)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/" + wizard.token + "/") as response:
            assert "Choose your agent" in response.read().decode()
            assert response.headers["Cache-Control"] == "no-store"
        with pytest.raises(HTTPError) as exc:
            urlopen(base + "/wrong/inspect")
        assert exc.value.code == 403
        request = Request(base + "/" + wizard.token + "/install", b'{}',
                          headers={"Content-Type": "application/json", "Origin": "https://example.org"})
        with pytest.raises(HTTPError) as exc:
            urlopen(request)
        assert exc.value.code == 403
        request = Request(base + "/" + wizard.token + "/install", b"x" * 4097,
                          headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as exc:
            urlopen(request)
        assert exc.value.code == 400
        assert not wizard.home.exists()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
