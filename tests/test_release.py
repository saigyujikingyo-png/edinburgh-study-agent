import json
import subprocess
import sys
from pathlib import Path
import pytest
from scripts import install_runtime
from scripts.public_release import (
    PublicationError, audit_index, audit_source, check_content, source_files,
)


@pytest.mark.parametrize("text", [
    "sk-" + "a" * 32,
    "tunnel_" + "a" * 32,
    "https://chatgpt.com/" + "c/" + "private-chat",
    "C:" + "\\" + "Users" + "\\" + "SyntheticUser" + "\\" + "notes",
    "s" + "1234567",
])
def test_release_rejects_private_patterns_without_printing_values(text):
    report = check_content("README.md", text.encode())
    assert report
    assert text not in json.dumps(report)


def test_mcp_template_cannot_hide_arbitrary_runtime_config():
    data = {"mcpServers": {"edinburgh-study": {"command": "personal-python"}}}
    assert check_content(".mcp.json", json.dumps(data).encode())


def test_release_blocks_private_files_in_public_directories(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "transcript.sqlite3").write_bytes(b"private")
    with pytest.raises(PublicationError):
        source_files(tmp_path)


def test_release_excludes_diagnostics_and_build_outputs(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/inspect_portals.py").write_text("private diagnostic")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist/old.zip").write_bytes(b"old")
    (tmp_path / "README.md").write_text("Public example")
    assert audit_source(tmp_path)["files"] == 1


def test_index_audit_reads_staged_blob_not_cleaned_working_tree(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    path = tmp_path / "README.md"
    path.write_text("ghp_" + "x" * 32)
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    path.write_text("Now clean")
    report = audit_index(tmp_path)
    assert report["passed"] is False
    assert report["issues"][0]["reason"] == "GitHub token"


def test_installer_keeps_checkout_portable_and_ignores_stale_wheel(tmp_path, monkeypatch):
    package = tmp_path / "source"
    package.mkdir()
    (package / ".mcp.json").write_text("portable marker")
    (package / "dist").mkdir()
    (package / "dist/edinburgh_study_agent-0.1.0.whl").write_bytes(b"old")
    runtime = tmp_path / "private/runtime"
    python = runtime / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    commands = []
    monkeypatch.setattr(install_runtime.shutil, "which", lambda _: None)
    monkeypatch.setattr(install_runtime, "run", lambda args: commands.append(args))
    from edinburgh_study_agent.chatgpt import configure_installation
    unbound = configure_installation(runtime.parent)
    monkeypatch.setattr(install_runtime.subprocess, "run", lambda args, **kwargs:
                        subprocess.CompletedProcess(args, 0, stdout=json.dumps(unbound)))
    result = install_runtime.install(package, runtime)
    assert result["chatgpt_binding"]["acceptance"] == "configuration_only"
    assert result["chatgpt_binding"]["cloud_installation"] == "not_checked"
    assert commands == [[python, "-m", "pip", "install", package.resolve()]]
    assert (package / ".mcp.json").read_text() == "portable marker"
    assert Path(result["mcp_config"]).is_relative_to(runtime.parent)
    config = json.loads(Path(result["mcp_config"]).read_text())
    assert config["mcpServers"]["edinburgh-study"]["command"] == str(python)


def test_installer_rejects_source_as_plugin_destination(tmp_path):
    with pytest.raises(ValueError, match="separate"):
        install_runtime.install(tmp_path, tmp_path / "runtime", tmp_path)


def test_public_icon_is_valid_and_metadata_is_rejected():
    import struct
    import zlib
    root=Path(__file__).resolve().parents[1]
    data=(root/"assets/icon.png").read_bytes()
    assert check_content("assets/icon.png",data)==[]
    payload=b"Comment\x00private fixture"
    chunk=struct.pack(">I",len(payload))+b"tEXt"+payload+struct.pack(">I",zlib.crc32(b"tEXt"+payload))
    assert check_content("assets/icon.png",data[:-12]+chunk+data[-12:])
    assert check_content("assets/other.png",data)
    assert check_content("assets/icon.png",b"not an image")


def test_public_svg_rejects_active_content():
    root=Path(__file__).resolve().parents[1]
    assert check_content("assets/icon.svg",(root/"assets/icon.svg").read_bytes())==[]
    assert check_content("assets/icon.svg",b'<svg xmlns="http://www.w3.org/2000/svg"><script>bad</script></svg>')


def test_installer_reapplies_saved_chatgpt_binding_to_private_plugin(tmp_path, monkeypatch):
    package = tmp_path / "source"
    package.mkdir()
    runtime = tmp_path / "private/runtime"
    python = runtime / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    settings = runtime.parent / "work/chatgpt.json"
    settings.parent.mkdir()
    settings.write_text("{}")
    plugin = tmp_path / "plugins/edinburgh-study-agent"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin/plugin.json").write_text("{}")
    commands = []
    monkeypatch.setattr(install_runtime.shutil, "which", lambda _: None)
    monkeypatch.setattr(install_runtime, "run", lambda _: None)
    def invoke(args, **kwargs):
        commands.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout='{"binding_configured":true,"cloud_connection":"not_checked"}')
    monkeypatch.setattr(install_runtime.subprocess, "run", invoke)
    result = install_runtime.install(package, runtime, plugin)
    assert commands[0][0] == [str(python), "-m", "edinburgh_study_agent.chatgpt", "configure",
                              "--home", str(runtime.parent), "--plugin-path", str(plugin)]
    assert result["chatgpt_binding"]["binding_configured"]
    assert result["chatgpt_binding"]["cloud_connection"] == "not_checked"


def test_installer_binding_failure_preserves_both_runtime_configs(tmp_path, monkeypatch):
    package = tmp_path / "source"
    package.mkdir()
    runtime = tmp_path / "private/runtime"
    python = runtime / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    plugin = tmp_path / "plugins/edinburgh-study-agent"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin/plugin.json").write_text("{}")
    saved_config = runtime.parent / "mcp.json"
    plugin_config = plugin / ".mcp.json"
    saved_config.write_text("original private config")
    plugin_config.write_text("original plugin config")
    monkeypatch.setattr(install_runtime.shutil, "which", lambda _: None)
    monkeypatch.setattr(install_runtime, "run", lambda _: None)
    def fail_binding(args, **kwargs):
        assert kwargs["shell"] is False
        raise subprocess.CalledProcessError(2, args)
    monkeypatch.setattr(install_runtime.subprocess, "run", fail_binding)
    with pytest.raises(subprocess.CalledProcessError):
        install_runtime.install(package, runtime, plugin, chatgpt_app_id="asdk_app_" + "a" * 32)
    assert saved_config.read_text() == "original private config"
    assert plugin_config.read_text() == "original plugin config"
