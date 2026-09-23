"""Only synthetic adapter observations; never toggle a user's VPN."""
import json
import os
import subprocess
from types import SimpleNamespace

import pytest
from edinburgh_study_agent import nmr_network


@pytest.mark.parametrize("adapter,state,active", [
    ({"detected": True, "active": False}, "vpn_disconnected", False),
    ({"detected": True, "active": True}, "vpn_active_service_unreachable", True),
    ({"detected": False, "active": False}, "network_unavailable", None),
    (None, "network_unavailable", None),
])
def test_guidance_distinguishes_adapter_hint_from_service_access(monkeypatch, adapter, state, active):
    monkeypatch.setattr(nmr_network, "vpn_adapter", lambda: adapter)
    value = nmr_network.failure_guidance()
    assert value["network"]["state"] == state
    assert value["network"]["vpn_adapter_active"] is active
    assert value["network"]["observed_at"]
    assert value["automatic_retry"] is False
    assert "retained" in value["message"] and "FortiClient" in value["message"]


@pytest.mark.skipif(os.name != "nt", reason="Windows adapter subprocess")
def test_adapter_probe_is_hidden_read_only_and_bounded(monkeypatch):
    seen = []
    def run(args, **kwargs):
        seen.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"detected":true,"active":false}')
    monkeypatch.setattr(nmr_network.subprocess, "run", run)
    assert nmr_network.vpn_adapter() == {"detected": True, "active": False}
    args, kwargs = seen[0]
    assert kwargs["timeout"] == 4 and kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert "Get-NetAdapter" in args[-1]
    assert "Connect" not in args[-1] and "Set-" not in args[-1]
    assert "Password" not in args[-1]


@pytest.mark.skipif(os.name != "nt", reason="Windows adapter subprocess")
@pytest.mark.parametrize("payload", ["SECRET", "[]", '{"detected":true,"active":"yes"}',
                                    '{"detected":false,"active":true}', "x"*1025])
def test_bad_adapter_output_is_unknown_and_never_echoed(monkeypatch, payload):
    monkeypatch.setattr(nmr_network.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout=payload))
    assert nmr_network.vpn_adapter() is None


@pytest.mark.skipif(os.name != "nt", reason="Windows adapter subprocess")
def test_probe_timeout_has_no_retry_or_sensitive_error(monkeypatch):
    count = []
    def fail(*args, **kwargs):
        count.append(1)
        raise subprocess.TimeoutExpired("PRIVATE", 4)
    monkeypatch.setattr(nmr_network.subprocess, "run", fail)
    assert nmr_network.vpn_adapter() is None
    assert count == [1]
