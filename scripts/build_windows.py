"""Build a self-contained Windows x64 installer from pinned public inputs.

Run on Windows. Only reviewed source wheels and downloaded distribution wheels
enter the bundle; never copy an installed personal runtime or data directory.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from public_release import audit_source

PYTHON_VERSION = "3.13.15"
PYTHON_URL = "https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-amd64.zip"
PYTHON_SHA256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(root, wheel, output):
    if sys.platform != "win32":
        raise ValueError("Build this Windows x64 package on Windows so environment markers match.")
    if not audit_source(root)["passed"]:
        raise ValueError("Public source audit failed.")
    version = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    if wheel.name != f"edinburgh_study_agent-{version}-py3-none-any.whl":
        raise ValueError("Supply the current version's freshly built wheel.")
    # Confirm the wheel contains the exact current application modules.
    with zipfile.ZipFile(wheel) as archive:
        expected = {"edinburgh_study_agent/" + path.name for path in (root / "src/edinburgh_study_agent").glob("*.py")}
        actual = {name for name in archive.namelist() if name.startswith("edinburgh_study_agent/") and not name.endswith("/")}
        if actual != expected:
            raise ValueError("Wheel package inventory differs from current reviewed source; rebuild from a clean build directory.")
        for path in (root / "src/edinburgh_study_agent").glob("*.py"):
            if archive.read("edinburgh_study_agent/" + path.name) != path.read_bytes():
                raise ValueError("Wheel and current source differ: " + path.name)
    cache = root / "build/download-cache"
    cache.mkdir(parents=True, exist_ok=True)
    python_zip = cache / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    if not python_zip.is_file() or digest(python_zip) != PYTHON_SHA256:
        temporary = python_zip.with_suffix(".download")
        with urllib.request.urlopen(PYTHON_URL, timeout=90) as response, temporary.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if digest(temporary) != PYTHON_SHA256:
            temporary.unlink()
            raise ValueError("Python distribution checksum does not match the official release.")
        temporary.replace(python_zip)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="windows-bundle-", dir=root / "build") as temporary:
        stage = Path(temporary)
        package = stage / "UoE-Companion"
        payload = package / "payload"
        runtime = payload / "runtime"
        scripts = runtime / "Scripts"
        libraries = runtime / "Lib/site-packages"
        scripts.mkdir(parents=True)
        libraries.mkdir(parents=True)
        with zipfile.ZipFile(python_zip) as archive:
            if any(Path(name).is_absolute() or ".." in Path(name).parts for name in archive.namelist()):
                raise ValueError("Unexpected path in the Python distribution.")
            archive.extractall(scripts)
        (scripts / "python313._pth").write_text("python313.zip\n.\n../Lib/site-packages\nimport site\n", encoding="ascii")
        (scripts / "sitecustomize.py").write_text(
            "import os, site\nsite.addsitedir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Lib', 'site-packages')))\n",
            encoding="ascii")
        wheels = stage / "wheels"
        wheels.mkdir()
        subprocess.run([sys.executable, "-m", "pip", "download", "--quiet", "--only-binary=:all:",
            "--platform", "win_amd64", "--python-version", "313", "--implementation", "cp", "--abi", "cp313",
            "--constraint", str(root / "requirements.lock"), "--dest", str(wheels), str(wheel)], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-index", "--no-compile",
            "--only-binary=:all:", "--platform", "win_amd64", "--python-version", "313", "--implementation", "cp", "--abi", "cp313",
            "--target", str(libraries), "--find-links", str(wheels), f"edinburgh-study-agent=={version}"], check=True)
        # pip's provenance can contain the local build path; replace it with public wheel hashes.
        for path in libraries.glob("*.dist-info/direct_url.json"):
            path.unlink()
        # Module entrypoints are used throughout. Discard pip's unused console
        # launchers, whose shebangs refer to the build interpreter.
        for name in ("bin", "Scripts"):
            generated=libraries/name
            if generated.is_dir():
                if generated.resolve().parent != libraries.resolve():
                    raise ValueError("Unexpected generated launcher directory.")
                shutil.rmtree(generated)
        for record in libraries.glob("*.dist-info/RECORD"):
            with record.open(newline="",encoding="utf-8") as stream:
                rows=list(csv.reader(stream))
            with record.open("w",newline="",encoding="utf-8") as stream:
                csv.writer(stream).writerows(row for row in rows
                    if (libraries/row[0]).resolve().is_relative_to(libraries.resolve()) and (libraries/row[0]).is_file())
        provenance = {"python": {"version": PYTHON_VERSION, "url": PYTHON_URL, "sha256": PYTHON_SHA256},
                      "wheels": {p.name: digest(p) for p in sorted(wheels.glob("*.whl"))}}
        (payload / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        shutil.copyfile(root / "scripts/Install.cmd", package / "Install.cmd")
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            shutil.copyfile(root / name, package / name)
        (package / "START-HERE.txt").write_text(
            "UoE Companion " + version + " - Windows x64 student preview\n\n"
            "1. Extract this entire ZIP to a local folder.\n"
            "2. Double-click Install.cmd. Choose your agent and install.\n"
            "3. Reload that agent's MCP connection. Sign in to school only when needed.\n\n"
            "Python and dependencies are included; Git and a development environment are not required.\n"
            "WorkBuddy and Claude Desktop configurations are merged with backups.\n"
            "New ChatGPT accounts still need their own private platform connection. Existing connections are preserved.\n"
            "Google Chrome or Microsoft Edge must be installed. Campus MFA remains your own step.\n"
            "Cloud Work needs your campus computer online. Individual host/model acceptance is documented separately.\n"
            "This is not a University product. Email is handled by Outlook.\n\n"
            "Guide: https://github.com/saigyujikingyo-png/edinburgh-study-agent/blob/v" + version + "/docs/EASY_INSTALL.md\n",
            encoding="utf-8")
        files = {p.relative_to(payload).as_posix(): digest(p) for p in sorted(runtime.rglob("*")) if p.is_file()}
        manifest = {"product": "uoe-companion", "version": version, "platform": "windows-x64",
                    "python": PYTHON_VERSION, "files": files}
        (payload / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        destination = output / f"UoE-Companion-{version}-Windows-x64.zip"
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    info=zipfile.ZipInfo("UoE-Companion/"+path.relative_to(package).as_posix())
                    info.compress_type=zipfile.ZIP_DEFLATED
                    info.external_attr=0o100644<<16
                    archive.writestr(info,path.read_bytes(),compresslevel=6)
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() is not None:
                raise ValueError("Installer ZIP integrity verification failed.")
        checksum = digest(destination)
        destination.with_suffix(".zip.sha256").write_text(checksum + "  " + destination.name + "\n", encoding="ascii")
        return {"archive": str(destination), "sha256": checksum, "bytes": destination.stat().st_size,
                "runtime_files": len(files), "python": PYTHON_VERSION, "version": version}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(root, args.wheel.resolve(), root / "dist")))


if __name__ == "__main__":
    main()
