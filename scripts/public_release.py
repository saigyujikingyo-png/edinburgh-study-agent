"""Audit explicit source inputs and exact Git-index blobs before publication."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

TOP_FILES = {
    ".gitignore", ".gitattributes", ".mcp.json", "pyproject.toml",
    "requirements.lock", "README.md", "VERIFICATION.md", "LICENSE",
    "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md",
}
SCRIPT_FILES = {
    "install_runtime.py", "run_server.py", "smoke_mcp.py", "verify_runtime.py",
    "package_plugin.py", "public_release.py", "Connect-Work.ps1",
    "Enable-Work-Connection.ps1", "Run-Work-Connection.ps1",
    "Stop-Work-Connection.ps1",
}
SOURCE_ROOTS = {".codex-plugin", ".github", "src", "scripts", "tests", "docs", "skills"}
PATTERNS = [
    ("personal Windows path", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+", re.I)),
    ("personal Unix path", re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("API key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("private tunnel identifier", re.compile(r"\btunnel_[a-f0-9]{16,}\b")),
    ("private app identifier", re.compile(r"\basdk_app_[a-f0-9]{16,}\b")),
    ("private chat link", re.compile(r"https://chatgpt\.com/c/[A-Za-z0-9-]+")),
    ("campus account identifier", re.compile(r"\b[su](?!0000000\b)\d{7}\b", re.I)),
    ("captured course identifier", re.compile(r"_\d{5,}_1\b")),
    ("signed URL", re.compile(r"[?&](?:X-Amz-Signature|SAMLResponse|access_token|id_token|signature)=[A-Za-z0-9%_+./=-]{24,}", re.I)),
]


class PublicationError(ValueError):
    pass


def allowed_path(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return False
    if name in TOP_FILES or name == ".codex-plugin/plugin.json":
        return True
    if len(path.parts) < 2:
        return False
    if path.parts[0] == "scripts":
        return len(path.parts) == 2 and path.name in SCRIPT_FILES
    if path.parts[0] in {"src", "tests"}:
        return path.suffix == ".py" and "__pycache__" not in path.parts
    if path.parts[0] in {"docs", "skills"}:
        return path.suffix == ".md"
    return (len(path.parts) == 3 and path.parts[:2] == (".github", "workflows")
            and path.suffix in {".yml", ".yaml"})


def check_content(name: str, data: bytes) -> list[dict]:
    if not allowed_path(name):
        return [{"file": name, "reason": "file is outside the public allowlist"}]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [{"file": name, "reason": "non-UTF-8 release input"}]
    issues = []
    for label, pattern in PATTERNS:
        match = pattern.search(text)
        if match:
            issues.append({"file": name, "reason": label,
                           "line": text[:match.start()].count("\n") + 1})
    if "\x00" in text:
        issues.append({"file": name, "reason": "binary content"})
    if name == ".mcp.json":
        expected = {"mcpServers": {"edinburgh-study": {
            "command": "python", "args": ["-m", "edinburgh_study_agent.server"],
            "env": {"PYTHONUTF8": "1"}}}}
        try:
            portable = json.loads(text) == expected
        except ValueError:
            portable = False
        if not portable:
            issues.append({"file": name, "reason": "MCP config is not the portable public template"})
    return issues


def source_files(root: Path) -> list[Path]:
    result = []
    for child in sorted(root.iterdir()):
        if child.name not in TOP_FILES | SOURCE_ROOTS:
            continue
        paths = [child] if not child.is_dir() else sorted(child.rglob("*"))
        if child.is_symlink():
            raise PublicationError("Release inputs cannot contain symlinks: " + child.name)
        for path in paths:
            name = path.relative_to(root).as_posix()
            if any(part == "__pycache__" or part.endswith(".egg-info") for part in path.parts):
                continue
            if path.parent == root / "scripts" and path.name not in SCRIPT_FILES:
                if path.name.startswith(("inspect_", "diagnose_")) or path.name == "download_live.py":
                    continue
            if path.is_symlink():
                raise PublicationError("Release inputs cannot contain symlinks: " + name)
            if path.is_dir():
                continue
            if not allowed_path(name):
                raise PublicationError("Unexpected file in release source tree: " + name)
            result.append(path)
    return result


def audit_source(root: Path) -> dict:
    files = source_files(root)
    issues = []
    for path in files:
        issues.extend(check_content(path.relative_to(root).as_posix(), path.read_bytes()))
    return {"passed": not issues, "scope": "allowlisted_source",
            "files": len(files), "issues": issues}


def audit_index(root: Path) -> dict:
    raw = subprocess.run(["git", "ls-files", "--stage", "-z"], cwd=root,
                         check=True, capture_output=True).stdout
    issues = []
    count = 0
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, name_bytes = record.split(b"\t", 1)
        mode, oid, stage = meta.decode("ascii").split()
        name = name_bytes.decode("utf-8")
        count += 1
        if mode not in {"100644", "100755"} or stage != "0":
            issues.append({"file": name, "reason": "symlink, submodule or unresolved Git entry"})
            continue
        data = subprocess.run(["git", "cat-file", "blob", oid], cwd=root,
                              check=True, capture_output=True).stdout
        issues.extend(check_content(name, data))
    if not count:
        issues.append({"file": "(index)", "reason": "empty publication index"})
    return {"passed": not issues, "scope": "exact_git_index_blobs",
            "files": count, "issues": issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-index", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        result = audit_index(root) if args.git_index else audit_source(root)
    except (PublicationError, subprocess.CalledProcessError) as exc:
        result = {"passed": False, "issues": [{"reason": str(exc)}]}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
