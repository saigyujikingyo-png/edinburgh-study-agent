import json
from pathlib import Path
import pytest
from edinburgh_study_agent.chatgpt import bind, inspect_binding
from edinburgh_study_agent import chatgpt
from scripts.public_release import check_content

APP = "asdk_app_" + "a" * 32


@pytest.fixture
def installation(tmp_path):
    plugin = tmp_path / "plugins/edinburgh-study-agent"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin/plugin.json").write_text(json.dumps({
        "name": "edinburgh-study-agent", "mcpServers": "./.mcp.json",
        "interface": {"displayName": "UoE Companion"}}))
    (plugin / ".mcp.json").write_text("keep local runtime")
    return tmp_path / "private", plugin


def test_private_binding_preserves_other_apps_and_runtime_and_reapplies_after_update(installation):
    home, plugin = installation
    app = plugin / ".app.json"
    app.write_text(json.dumps({"apps": {"other": {"id": "unrelated"}}}))
    initial_manifest = (plugin / ".codex-plugin/plugin.json").read_bytes()
    result = bind(home, plugin, APP)
    assert result["binding_configured"] and result["changed"]
    assert result["cloud_connection"] == "not_checked"
    assert result["chat_model_roundtrip"] == "not_checked"
    assert result["work_model_roundtrip"] == "not_checked"
    assert json.loads(app.read_text())["apps"]["other"] == {"id": "unrelated"}
    assert (plugin / ".mcp.json").read_text() == "keep local runtime"
    assert not bind(home, plugin)["changed"]
    assert Path(result["backup"]).is_relative_to(home)
    # A portable upgrade copies its clean manifest. The saved association repairs it.
    (plugin / ".codex-plugin/plugin.json").write_bytes(initial_manifest)
    assert not inspect_binding(home, plugin)["binding_configured"]
    assert bind(home, plugin)["binding_configured"]


def test_binding_refuses_retargeting_and_git_checkout(installation):
    home, plugin = installation
    bind(home, plugin, APP)
    before = (plugin / ".app.json").read_bytes()
    with pytest.raises(ValueError, match="different personal"):
        bind(home, plugin, "asdk_app_" + "b" * 32)
    assert (plugin / ".app.json").read_bytes() == before
    (plugin / ".git").write_text("gitdir: elsewhere")
    with pytest.raises(ValueError, match="Git checkout"):
        bind(home, plugin, APP)


def test_binding_rolls_back_when_later_write_fails(installation, monkeypatch):
    home, plugin = installation
    before = (plugin / ".codex-plugin/plugin.json").read_bytes()
    original = chatgpt.atomic_json
    def fail_settings(path, value):
        if path.name == "chatgpt.json":
            raise OSError("synthetic write failure")
        original(path, value)
    monkeypatch.setattr(chatgpt, "atomic_json", fail_settings)
    with pytest.raises(OSError):
        bind(home, plugin, APP)
    assert (plugin / ".codex-plugin/plugin.json").read_bytes() == before
    assert not (plugin / ".app.json").exists()


def test_unbound_status_does_not_claim_cloud_or_login(installation):
    home, plugin = installation
    value = inspect_binding(home, plugin)
    assert not value["binding_configured"] and value["campus_login"] == "not_checked"
    assert value["connection_url"] is None
    with pytest.raises(ValueError, match="app ID"):
        bind(home, plugin, "https://example.test")


def test_public_package_rejects_personal_app_dependency():
    assert check_content(".app.json", json.dumps({"apps": {"uoe-companion": {"id": APP}}}).encode())
    assert check_content(".codex-plugin/plugin.json", b'{"apps":"./.app.json"}')
