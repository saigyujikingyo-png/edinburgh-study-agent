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
            locked: bool = False) -> dict:
    package, runtime = package.resolve(), runtime.resolve()
    if plugin is not None:
        plugin = plugin.resolve()
        if plugin == package:
            raise ValueError("Use a separate extracted plugin path; the source config stays portable.")
        if not (plugin / ".codex-plugin/plugin.json").is_file():
            raise ValueError("Target must be an extracted UoE Companion plugin.")
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
    return {"python": str(python), "mcp_config": str(destination),
            "plugin_config": str(plugin / ".mcp.json") if plugin else None,
            "host_configuration_changed": False, "source_config_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-path", type=Path, help="Optional separate extracted plugin.")
    parser.add_argument("--runtime", type=Path, default=Path.home() / ".edinburgh-study-agent/runtime")
    parser.add_argument("--locked", action="store_true", help="Use the recorded dependency snapshot.")
    args = parser.parse_args()
    try:
        result = install(Path(__file__).resolve().parents[1], args.runtime,
                         args.plugin_path, args.locked)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
