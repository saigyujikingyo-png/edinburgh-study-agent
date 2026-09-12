"""Install current source in a private runtime without changing the source config."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(args):
    subprocess.run([str(x) for x in args], check=True)


def install(package: Path, runtime: Path, plugin: Path | None = None,
            locked: bool = False, chatgpt_app_id: str | None = None) -> dict:
    package, runtime = package.resolve(), runtime.resolve()
    if plugin is not None:
        plugin = plugin.resolve()
        if plugin == package:
            raise ValueError("Use a separate extracted plugin path; the source config stays portable.")
        if not (plugin / ".codex-plugin/plugin.json").is_file():
            raise ValueError("Target must be an extracted UoE Companion plugin.")
    if chatgpt_app_id and plugin is None:
        raise ValueError("Supply a separate private --plugin-path to bind ChatGPT.")
    uv = shutil.which("uv")
    python = runtime / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        run([uv, "venv", "--python", sys.executable, runtime] if uv else
            [sys.executable, "-m", "venv", runtime])
    installer = [uv, "pip", "install", "--python", python] if uv else [python, "-m", "pip", "install"]
    if locked:
        run(installer + ["-r", package / "requirements.lock"])
    # Always install this checkout. A stale dist wheel must not shadow the source.
    run(installer + [package])
    config = {"mcpServers": {"edinburgh-study": {
        "command": str(python), "args": ["-m", "edinburgh_study_agent.server"],
        "env": {"PYTHONUTF8": "1"}}}}
    destination = runtime.parent / "mcp.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    if plugin is not None:
        (plugin / ".mcp.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    chatgpt_binding = {"binding_configured": False, "cloud_connection": "not_checked"}
    if plugin is not None and (chatgpt_app_id or (runtime.parent / "work/chatgpt.json").exists()):
        command = [str(python), "-m", "edinburgh_study_agent.chatgpt", "bind",
                   "--home", str(runtime.parent), "--plugin-path", str(plugin)]
        if chatgpt_app_id:
            command += ["--app-id", chatgpt_app_id]
        completed = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
        chatgpt_binding = json.loads(completed.stdout)
    return {"python": str(python), "mcp_config": str(destination),
            "chatgpt_binding": chatgpt_binding,
            "plugin_config": str(plugin / ".mcp.json") if plugin else None,
            "host_configuration_changed": False, "source_config_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-path", type=Path, help="Optional separate extracted plugin.")
    parser.add_argument("--runtime", type=Path, default=Path.home() / ".edinburgh-study-agent/runtime")
    parser.add_argument("--chatgpt-app-id", help="Bind your own registered ChatGPT connection to the private plugin copy.")
    parser.add_argument("--locked", action="store_true", help="Use the recorded dependency snapshot.")
    args = parser.parse_args()
    try:
        result = install(Path(__file__).resolve().parents[1], args.runtime,
                         args.plugin_path, args.locked, args.chatgpt_app_id)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
