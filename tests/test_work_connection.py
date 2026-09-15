"""Exercise the Windows connection scripts without any real task or process access."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Connection supervisors use Windows identity/DPAPI facilities")

# Process/task cmdlets and the tunnel client are replaced at their external
# boundaries. The shipped scripts retain their control flow and write their real
# status/error receipts into the isolated fixture directory.
HARNESS = r"""
param([string]$ConfigPath)
$ErrorActionPreference = 'Stop'
$global:Fixture = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$global:Trace = [ordered]@{
    ConnectCalls = 0; StatusCalls = 0; RegistryStops = 0; ClientCalls = @(); Sleeps = @()
    Killed = @(); CimFilters = @(); SnapshotReads = 0; DisabledTasks = @(); StoppedTasks = @()
    MutexReleased = 0; MutexDisposed = 0; ConnectEnvironmentValid = $false; Failed = $false
}
$global:CurrentProcesses = @{}
function FixtureProcess($item) {
    [pscustomobject]@{ ProcessId = [int]$item.ProcessId; ParentProcessId = [int]$item.ParentProcessId
        ExecutablePath = $item.ExecutablePath; CommandLine = $item.CommandLine
        CreationDate = [DateTime]::Parse($item.CreationDate) }
}
foreach ($item in @($Fixture.current)) {
    if ($item) { $CurrentProcesses[[string]$item.ProcessId] = FixtureProcess $item }
}
function New-Object {
    param([string]$TypeName, [object[]]$ArgumentList)
    if ($TypeName -ne 'Threading.Mutex') { throw "Unexpected New-Object boundary: $TypeName" }
    $mock = [pscustomobject]@{}
    $mock | Add-Member ScriptMethod WaitOne { param($Milliseconds) return $true }
    $mock | Add-Member ScriptMethod ReleaseMutex { $global:Trace.MutexReleased++ }
    $mock | Add-Member ScriptMethod Dispose { $global:Trace.MutexDisposed++ }
    return $mock
}
function ConvertTo-SecureString {
    param([string]$String)
    if ($String -ne 'synthetic-encrypted-placeholder') { throw 'Unexpected secret fixture' }
    $key = [Security.SecureString]::new()
    foreach ($character in ('s' + 'k-synthetic-test-value').ToCharArray()) { $key.AppendChar($character) }
    return $key
}
function Start-Sleep { param([int]$Seconds) $global:Trace.Sleeps += $Seconds }
function Get-Process {
    [CmdletBinding()] param([int]$Id)
    [pscustomobject]@{Id = $Id; StartTime = [datetime]'2026-09-15T00:00:00Z'}
}
function Get-ScheduledTask {
    [CmdletBinding()] param([string]$TaskName)
    if ($Fixture.task) { return $Fixture.task }
}
function Disable-ScheduledTask {
    [CmdletBinding()] param([string]$TaskName)
    $global:Trace.DisabledTasks += $TaskName
}
function Stop-ScheduledTask {
    [CmdletBinding()] param([string]$TaskName)
    $global:Trace.StoppedTasks += $TaskName
}
function Get-CimInstance {
    [CmdletBinding()] param([string]$ClassName, [string]$Filter)
    if ($ClassName -ne 'Win32_Process') { throw 'Unexpected CIM class' }
    if (!$Filter) {
        $global:Trace.SnapshotReads++
        foreach ($item in @($Fixture.snapshot)) { if ($item) { FixtureProcess $item } }
        return
    }
    $global:Trace.CimFilters += $Filter
    if ($Filter -notmatch '^ProcessId = ([0-9]+)$') { throw 'Unexpected process query' }
    return $global:CurrentProcesses[$Matches[1]]
}
function Stop-Process {
    [CmdletBinding()] param([int]$Id)
    $global:Trace.Killed += $Id
    $global:CurrentProcesses.Remove([string]$Id)
}
$env:CONTROL_PLANE_API_KEY = 'fixture-prior-key'
$env:PYTHONUTF8 = 'fixture-prior-utf8'
$global:LASTEXITCODE = 0
try {
    if ($Fixture.mode -eq 'run') { $scriptOutput = & $Fixture.script -ConnectOnce }
    else { $scriptOutput = & $Fixture.script }
} catch {
    $global:Trace.Failed = $true
    $global:Trace.FailureMessage = $_.Exception.Message
}
$Trace.EnvironmentRestored = ($env:CONTROL_PLANE_API_KEY -eq 'fixture-prior-key' -and $env:PYTHONUTF8 -eq 'fixture-prior-utf8')
$Trace.ExitCode = $LASTEXITCODE
foreach ($name in @('status', 'error')) {
    $path = Join-Path $Fixture.workRoot ($name + '.json')
    if (Test-Path -LiteralPath $path) { $Trace[$name] = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
}
$Trace | ConvertTo-Json -Depth 20 -Compress
"""

CLIENT = r"""
$global:Trace.ClientCalls += ,@($args)
$global:LASTEXITCODE = 0
switch ($args[1]) {
    'connect' {
        $global:Trace.ConnectCalls++
        $global:Trace.ConnectEnvironmentValid = ($env:CONTROL_PLANE_API_KEY.StartsWith('s' + 'k-') -and $env:PYTHONUTF8 -eq '1')
        '{}'
        if ($global:Fixture.connectFails) { $global:LASTEXITCODE = 1 }
    }
    'status' {
        $index = [Math]::Min($global:Trace.StatusCalls, $global:Fixture.statuses.Count - 1)
        $global:Trace.StatusCalls++
        $global:Fixture.statuses[$index] | ConvertTo-Json -Depth 10 -Compress
    }
    'stop' {
        $global:Trace.RegistryStops++
        foreach ($id in @($global:Fixture.registryRemoves)) { $global:CurrentProcesses.Remove([string]$id) }
    }
    default { throw 'Unexpected client invocation' }
}
"""


@pytest.fixture(scope="module")
def powershell() -> str:
    command = shutil.which("pwsh") or shutil.which("powershell")
    if not command:
        pytest.skip("PowerShell is required for supervisor behavior tests")
    return command


def setup_fixture(tmp_path: Path, mode: str) -> dict:
    fixture_home = tmp_path / "Synthetic User"
    study_root = fixture_home / ".edinburgh-study-agent"
    work_root = study_root / "work"
    secret_root = study_root / "secrets"
    work_root.mkdir(parents=True)
    secret_root.mkdir()
    client = work_root / "synthetic-tunnel-client.ps1"
    client.write_text(CLIENT, encoding="utf-8")
    python = study_root / "python.exe"
    python.write_bytes(b"")
    settings = {"alias": "edinburgh-study-agent", "tunnel_id": "tunnel_" + "a" * 32,
                "profile_directory": str(work_root / "profiles"), "client": str(client), "python": str(python)}
    (work_root / "connection.json").write_text(json.dumps(settings), encoding="utf-8")
    (secret_root / "work-tunnel-key.dpapi").write_text("synthetic-encrypted-placeholder", encoding="utf-8")
    source = SCRIPTS / ("Run-Work-Connection.ps1" if mode == "run" else "Stop-Work-Connection.ps1")
    code = source.read_text(encoding="utf-8-sig")
    location = "[Environment]::GetFolderPath('UserProfile')"
    assert code.count(location) == 1, "Test fixture needs the script's user-data directory boundary"
    # Only relocate the user-data root. No readiness, matching, retry or cleanup
    # statement is replaced, so mutations in those behaviors reach these tests.
    code = code.replace(location, "'" + str(fixture_home).replace("'", "''") + "'")
    script = tmp_path / source.name
    script.write_text(code, encoding="utf-8-sig")
    return {"mode": mode, "script": str(script), "workRoot": str(work_root), "settings": settings,
            "statuses": [], "snapshot": [], "current": [], "registryRemoves": []}


def invoke(powershell: str, tmp_path: Path, config: dict) -> dict:
    harness = tmp_path / "fixture.ps1"
    harness.write_text(HARNESS, encoding="utf-8-sig")
    arguments = tmp_path / "fixture.json"
    arguments.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-File", str(harness), str(arguments)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


def status(*, ready: bool) -> dict:
    return {"process_running": True, "healthy": ready, "ready": ready, "process": {"pid": 27001}}


def test_starting_daemon_is_polled_until_ready_without_reconnecting(powershell, tmp_path):
    config = setup_fixture(tmp_path, "run")
    config["statuses"] = [status(ready=False), status(ready=False), status(ready=True)]
    trace = invoke(powershell, tmp_path, config)
    assert trace["Failed"] is False
    assert trace["ConnectCalls"] == 1
    assert trace["StatusCalls"] == 3
    assert trace["RegistryStops"] == 0
    assert trace["Sleeps"] == [1, 1]
    assert trace["status"]["ready"] is True
    assert trace["status"]["pid"] == 27001
    assert trace["status"]["verification_scope"] == "transport_only"
    assert trace["ConnectEnvironmentValid"] is True
    assert trace["EnvironmentRestored"] is True
    assert trace["MutexReleased"] == trace["MutexDisposed"] == 1
    assert "error" not in trace


def test_readiness_timeout_stops_created_daemon_before_failure(powershell, tmp_path):
    config = setup_fixture(tmp_path, "run")
    config["statuses"] = [status(ready=False)]
    trace = invoke(powershell, tmp_path, config)
    assert trace["Failed"] is True or trace["ExitCode"] != 0
    assert trace["ConnectCalls"] == 1
    assert trace["StatusCalls"] == 20
    assert trace["RegistryStops"] == 1
    assert trace["ClientCalls"][-1] == ["runtimes", "stop", "edinburgh-study-agent"]
    assert trace["Sleeps"] == [1] * 20
    assert trace["error"]["ready"] is False
    assert trace["EnvironmentRestored"] is True
    assert trace["MutexReleased"] == trace["MutexDisposed"] == 1
    assert "status" not in trace


def process(pid: int, executable: str, command: str, *, parent: int = 0, born: str = "2026-09-15T00:00:00Z") -> dict:
    return {"ProcessId": pid, "ParentProcessId": parent, "ExecutablePath": executable,
            "CommandLine": command, "CreationDate": born}


def daemon_command(settings: dict, *, alias: str | None = None, directory: str | None = None) -> str:
    return (f'"{settings["client"]}" run --profile "{alias or settings["alias"]}" '
            f'--profile-dir "{directory or settings["profile_directory"]}"')


def test_stop_cleans_old_exact_profile_daemons_and_children_only(powershell, tmp_path):
    config = setup_fixture(tmp_path, "stop")
    settings = config["settings"]
    command = daemon_command(settings)
    snapshot = [
        process(100, settings["client"], command),  # Older daemon absent from registry.
        process(101, settings["client"], command),  # Registry's current daemon.
        process(102, settings["client"], daemon_command(settings, alias="other-profile")),
        process(103, settings["client"], daemon_command(settings, directory=settings["profile_directory"] + "-other")),
        process(104, str(tmp_path / "origin-tunnel-client.exe"), command),
        process(105, settings["client"], daemon_command(settings, alias="edinburgh-study-agent-extra")),
        process(106, settings["client"], command),  # PID reused before final kill check.
        process(107, settings["client"], command),  # Executable changed before final kill check.
        process(110, settings["python"], 'python -m edinburgh_study_agent.server', parent=100),
        process(111, settings["python"], 'python -m origin_agent.server', parent=100),
        process(112, str(tmp_path / "other-python.exe"), 'python -m edinburgh_study_agent.server', parent=100),
        process(113, settings["python"], 'python -m edinburgh_study_agent.server', parent=102),
        process(114, settings["python"], 'python -m edinburgh_study_agent.server_extra', parent=100),
        process(115, settings["python"], 'python -m edinburgh_study_agent.server', parent=101),
    ]
    config["snapshot"] = snapshot
    config["current"] = [dict(item) for item in snapshot]
    next(item for item in config["current"] if item["ProcessId"] == 106)["CreationDate"] = "2026-09-15T01:00:00Z"
    next(item for item in config["current"] if item["ProcessId"] == 107)["ExecutablePath"] = str(tmp_path / "unrelated.exe")
    config["registryRemoves"] = [101]
    trace = invoke(powershell, tmp_path, config)
    assert trace["Failed"] is False
    assert trace["SnapshotReads"] == 1
    assert trace["RegistryStops"] == 1
    assert sorted(trace["Killed"]) == [100, 110, 115]
    assert trace["DisabledTasks"] == trace["StoppedTasks"] == []
    assert set(trace["CimFilters"]) == {f"ProcessId = {pid}" for pid in (100, 101, 106, 107, 110, 115)}


def test_stop_refuses_a_different_scheduled_task_before_touching_processes(powershell, tmp_path):
    config = setup_fixture(tmp_path, "stop")
    config["task"] = {"Actions": [{"Execute": "C:\\Unrelated\\powershell.exe", "Arguments": '-File "unrelated.ps1"'}]}
    trace = invoke(powershell, tmp_path, config)
    assert trace["Failed"] is True
    assert trace["RegistryStops"] == trace["SnapshotReads"] == 0
    assert trace["DisabledTasks"] == trace["StoppedTasks"] == trace["Killed"] == []


def test_failed_connect_cleans_unregistered_worker_before_retry(powershell, tmp_path):
    config = setup_fixture(tmp_path, "run")
    config["connectFails"] = True
    settings = config["settings"]
    config["snapshot"] = [
        process(201, settings["client"], daemon_command(settings)),
        process(202, settings["python"], 'python -m edinburgh_study_agent.server', parent=201),
        process(203, settings["client"], daemon_command(settings, alias="other-profile")),
    ]
    config["current"] = config["snapshot"]
    trace = invoke(powershell, tmp_path, config)
    assert trace["Failed"] or trace["ExitCode"] != 0
    assert trace["ConnectCalls"] == 1
    assert trace["StatusCalls"] == 0
    assert trace["RegistryStops"] == 1
    assert trace["Killed"] == [201, 202]
    assert trace["EnvironmentRestored"] is True
    assert trace["error"]["ready"] is False
