"""Bounded local VPN hints after a real NMR network failure; no credential access."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from .models import now_utc

NETWORK_ERRORS = frozenset({"NETWORK_UNAVAILABLE", "TRANSFER_FAILED"})


def vpn_adapter():
    """Report only Fortinet adapter presence/state, not names, routes or addresses."""
    if os.name != "nt":
        return None
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = (
        "$v = @(Get-NetAdapter -ErrorAction Stop | Where-Object "
        "{ $_.InterfaceDescription -match 'Fortinet.*(VPN|Virtual Ethernet)' }); "
        "@{ detected = ($v.Count -gt 0); active = "
        "(@($v | Where-Object { $_.Status -eq 'Up' }).Count -gt 0) } | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [str(executable), "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=4, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or len(result.stdout) > 1024:
            return None
        value = json.loads(result.stdout)
        if (not isinstance(value, dict) or set(value) != {"detected", "active"}
                or any(type(v) is not bool for v in value.values())
                or (value["active"] and not value["detected"])):
            return None
        return value
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def failure_guidance():
    """An active adapter is a hint, never proof of a working university VPN route."""
    adapter = vpn_adapter()
    active = adapter["active"] if adapter and adapter["detected"] else None
    if active is False:
        state = "vpn_disconnected"
        recovery = "connect_campus_vpn_then_resume"
        message = ("NMR is unreachable and the FortiClient VPN adapter is disconnected. "
                   "Off campus, connect FortiClient to the University of Edinburgh VPN "
                   "on the computer running UoE Companion, then resume this request.")
    elif active is True:
        state = "vpn_active_service_unreachable"
        recovery = "check_campus_vpn_or_service_then_resume"
        message = ("NMR is unreachable although a FortiClient VPN adapter is active. "
                   "This does not verify the campus route. Check the university VPN "
                   "connection and NMR service, then resume this request.")
    else:
        state = "network_unavailable"
        recovery = "check_campus_vpn_or_service_then_resume"
        message = ("NMR is unreachable; the campus VPN state could not be verified. "
                   "Off campus, connect FortiClient to the University of Edinburgh VPN "
                   "on the computer running UoE Companion, then resume this request.")
    return {"message": message + " Saved login and selections are retained; do not re-enter your password.",
            "network": {"state": state, "vpn_client": "FortiClient",
                        "vpn_adapter_active": active, "observed_at": now_utc().isoformat()},
            "recovery_action": recovery, "automatic_retry": False}
