"""Reuse an installed Chromium browser; no download or profile export at runtime."""
import os
from pathlib import Path
import shutil
import sys


def channel():
    chosen = os.environ.get("UOE_BROWSER_CHANNEL")
    if chosen:
        if chosen not in ("chrome", "msedge"):
            raise ValueError("UOE_BROWSER_CHANNEL must be chrome or msedge.")
        return chosen
    if sys.platform == "win32":
        roots = [Path(os.environ[name]) for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA") if os.environ.get(name)]
        for name, relative in (("chrome", "Google/Chrome/Application/chrome.exe"),
                               ("msedge", "Microsoft/Edge/Application/msedge.exe")):
            if any((root / relative).is_file() for root in roots):
                return name
    elif sys.platform == "darwin":
        for name, folder in (("chrome", "Google Chrome.app"), ("msedge", "Microsoft Edge.app")):
            if (Path("/Applications") / folder).exists():
                return name
    else:
        if shutil.which("google-chrome") or shutil.which("google-chrome-stable"):
            return "chrome"
        if shutil.which("microsoft-edge"):
            return "msedge"
    raise ValueError("Install Google Chrome or Microsoft Edge, then connect school again. No separate Python installation is needed for the Windows bundle.")
