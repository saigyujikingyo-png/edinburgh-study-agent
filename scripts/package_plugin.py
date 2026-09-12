"""Build a deterministic, validated public source/plugin archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from public_release import audit_source, source_files


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-label", help="Optional lowercase distribution label.")
    args = parser.parse_args()
    version = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,95}", version):
        parser.error("Invalid package version")
    if args.build_label:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,63}", args.build_label):
            parser.error("build-label must be a short lowercase filename label")
        version = version.split("+", 1)[0] + "-" + args.build_label
    report = audit_source(root)
    if not report["passed"]:
        raise SystemExit(json.dumps(report))
    files = source_files(root)
    destination = root / "dist" / f"edinburgh-study-agent-{version}.zip"
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo("edinburgh-study-agent/" + path.relative_to(root).as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive integrity check failed")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(
        digest + "  " + destination.name + "\n", encoding="ascii")
    print(json.dumps({"archive": str(destination), "files": len(files),
                      "sha256": digest, "publication_check": "passed"}))


if __name__ == "__main__":
    main()
