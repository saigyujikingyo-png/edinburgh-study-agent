"""Local, transactional installation of the reviewed Windows runtime bundle.

No school account data is bundled, uploaded, reset or copied between users.
The browser wizard and command-line checks use this same implementation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile

PRODUCT = "uoe-companion"
JSON_HOSTS = ("workbuddy", "claude-desktop")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_manifest(bundle):
    bundle = Path(bundle).resolve()
    document = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if document.get("product") != PRODUCT or not isinstance(document.get("files"), dict):
        raise ValueError("This is not a UoE Companion installation bundle.")
    if not document["files"] or len(document["files"]) > 20000:
        raise ValueError("Invalid bundle file inventory.")
    for name, expected in document["files"].items():
        parts = PurePosixPath(name)
        if (parts.is_absolute() or ".." in parts.parts or "\\" in name or ":" in name
                or not name.startswith("runtime/") or len(expected) != 64):
            raise ValueError("Invalid installation manifest path or checksum.")
        file = bundle / name
        if not file.resolve().is_relative_to(bundle) or file.is_symlink() or not file.is_file():
            raise ValueError("An installation file is missing or points outside the bundle.")
        if digest(file) != expected:
            raise ValueError("Installation checksum mismatch. Download the release again.")
    if "runtime/Scripts/python.exe" not in document["files"]:
        raise ValueError("The bundled Python runtime is missing.")
    return document


@contextmanager
def installation_lock(home):
    path = home / ".setup.lock"
    with path.open("a+b") as stream:
        try:
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("Another UoE installation is running. Wait for it to finish.") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def runtime_processes(runtime):
    """Check executable paths, without reading command lines or other app data."""
    if os.name != "nt" or not runtime.exists():
        return []
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    pids = (wintypes.DWORD * 8192)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(needed)):
        raise OSError("Could not check whether the runtime is in use.")
    active = []
    for pid in pids[:needed.value // ctypes.sizeof(wintypes.DWORD)]:
        if pid == os.getpid():
            continue
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        try:
            text = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(text))
            if kernel.QueryFullProcessImageNameW(handle, 0, text, ctypes.byref(length)):
                if Path(text.value).resolve().is_relative_to(runtime.resolve()):
                    active.append(pid)
        finally:
            kernel.CloseHandle(handle)
    return active


def config_targets(selected, override=None):
    from .hosts import configuration_path
    override = override or {}
    if any(name not in JSON_HOSTS for name in selected):
        raise ValueError("Automatic configuration supports WorkBuddy and Claude Desktop.")
    return {name: Path(override[name]) if name in override else configuration_path(name)
            for name in dict.fromkeys(selected)}


def inspect(home):
    from .hosts import configuration_path
    home = Path(home).resolve()
    receipt = home / "installation.json"
    version = None
    if receipt.is_file():
        version = json.loads(receipt.read_text(encoding="utf-8")).get("version")
    return {"home": str(home), "runtime_present": (home / "runtime/Scripts/python.exe").is_file(),
            "version": version,
            "hosts": {name: configuration_path(name).parent.exists() for name in JSON_HOSTS},
            "chatgpt_connection_present": (home / "work/connection.json").is_file(),
            "campus_profile_present": (home / "school/profile").is_dir()}


def run_doctor(python, private_home, profile="daily"):
    env = {**os.environ, "PYTHONUTF8": "1"}
    completed = subprocess.run(
        [str(python), "-m", "edinburgh_study_agent.hosts", "doctor", "--home", str(private_home),
         "--profile", profile], env=env, capture_output=True, text=True, encoding="utf-8",
        timeout=65, check=True, creationflags=0x08000000 if os.name == "nt" else 0)
    return json.loads(completed.stdout)


def remove_owned_stage(path, home):
    path, home = Path(path).resolve(), Path(home).resolve()
    if path.parent != home or not path.name.startswith(".setup-stage-") or path.is_symlink():
        raise ValueError("Refusing to remove an unexpected installation staging directory.")
    if path.exists():
        shutil.rmtree(path)


def install(bundle, home, selected=(), *, config_paths=None, progress=lambda value: None,
            doctor=run_doctor):
    from .hosts import atomic_json, merge_config, server_config, generate
    bundle, home = Path(bundle).resolve(), Path(home).resolve()
    if home == Path.home().resolve() or home.parent == home or home.is_relative_to(bundle):
        raise ValueError("Choose a separate UoE private data directory.")
    home.mkdir(parents=True, exist_ok=True)
    with installation_lock(home):
        progress("Checking package integrity")
        manifest = read_manifest(bundle)
        runtime = home / "runtime"
        targets = config_targets(selected, config_paths)
        original = {path: path.read_bytes() if path.exists() else None for path in targets.values()}
        # Preflight all selected configs before replacing a working runtime.
        for content in original.values():
            if content is not None:
                doc = json.loads(content.decode("utf-8-sig"))
                if not isinstance(doc, dict) or not isinstance(doc.get("mcpServers", {}), dict):
                    raise ValueError("An existing host configuration is invalid; nothing was replaced.")
        previous = home / "installation.json"
        prior_receipt = json.loads(previous.read_text(encoding="utf-8")) if previous.is_file() else {}
        same = prior_receipt.get("bundle_sha256") == digest(bundle / "manifest.json")
        if same:
            same = all((home / name).is_file() and digest(home / name) == value
                       for name, value in manifest["files"].items())
        if not same and runtime_processes(runtime):
            raise ValueError("UoE is in use. Finish school jobs, reload/close its MCP clients and pause the existing Work connection, then retry. Data and login are preserved.")
        stage = Path(tempfile.mkdtemp(prefix=".setup-stage-", dir=home))
        backup = None
        promoted = False
        applied = {}
        try:
            if not same:
                progress("Installing the bundled runtime")
                for name in manifest["files"]:
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(bundle / name, target)
                progress("Checking the installed tools")
                check = doctor(stage / "runtime/Scripts/python.exe", stage / "check-data")
                if check.get("version") != manifest["version"]:
                    raise ValueError("Installed version did not match the package.")
                if runtime.exists():
                    backup = home / ("runtime-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
                    os.replace(runtime, backup)
                os.replace(stage / "runtime", runtime)
                promoted = True
            else:
                progress("This version is already installed; verifying connection")
                check = doctor(runtime / "Scripts/python.exe", stage / "check-data")
            config = server_config(runtime / "Scripts/python.exe", home, profile="daily")
            receipts = []
            for host, path in targets.items():
                if (path.read_bytes() if path.exists() else None) != original[path]:
                    raise ValueError("A client configuration changed during installation; retry.")
                progress("Connecting " + host)
                existing=json.loads(original[path].decode("utf-8-sig")) if original[path] else {}
                managed=[entry for entry in existing.get("mcpServers",{}).values()
                         if isinstance(entry,dict) and entry.get("args")==["-m","edinburgh_study_agent.server"]]
                locale=managed[0].get("env",{}).get("UOE_LOCALE","auto") if len(managed)==1 else "auto"
                host_config=server_config(runtime / "Scripts/python.exe",home,locale=locale,profile="daily")
                receipts.append({"host": host, **merge_config(path, host_config)})
                applied[path] = path.read_bytes()
            # Generic documents are private; existing configurations and Work identity are untouched.
            connections = home / "connections" / ("setup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
            generate(connections, config)
            receipt = {"product": PRODUCT, "version": manifest["version"],
                       "bundle_sha256": digest(bundle / "manifest.json"), "home": str(home),
                       "python": str(runtime / "Scripts/python.exe"), "unchanged_runtime": same,
                       "runtime_backup": str(backup) if backup else prior_receipt.get("runtime_backup"),
                       "hosts": receipts, "connection_documents": str(connections), "check": check,
                       "campus_login_preserved": True, "host_model_roundtrip": "not_tested"}
            atomic_json(previous, receipt)
            progress("Installation complete. Reload your agent's MCP connection.")
            return receipt
        except Exception:
            for path, after in applied.items():
                if path.is_file() and path.read_bytes() == after:
                    if original[path] is None:
                        path.unlink()
                    else:
                        path.write_bytes(original[path])
            if promoted:
                os.replace(runtime, stage / "runtime")
            if backup is not None and backup.exists():
                os.replace(backup, runtime)
            raise
        finally:
            remove_owned_stage(stage, home)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "inspect", "login"])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--home", type=Path, default=Path.home() / ".edinburgh-study-agent")
    parser.add_argument("--host", action="append", choices=JSON_HOSTS, default=[])
    parser.add_argument("--config-map", type=Path, help="Isolated acceptance host paths; not needed by students.")
    args = parser.parse_args()
    try:
        if args.action == "inspect":
            value = inspect(args.home)
        elif args.action == "login":
            from .store import Store
            from . import school
            value = school.start_job(Store(args.home), "login")
        else:
            if args.bundle is None:
                parser.error("--bundle is required")
            paths = json.loads(args.config_map.read_text(encoding="utf-8")) if args.config_map else None
            value = install(args.bundle, args.home, args.host, config_paths=paths,
                            progress=lambda text: print(text, file=sys.stderr, flush=True))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__":
    main()
