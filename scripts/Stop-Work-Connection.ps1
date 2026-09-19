# UoE release-owned launch shim. Policy lives in the installed Python package.
param([switch]$ConnectOnce)
$ErrorActionPreference = 'Stop'
$workRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $workRoot 'connection.json') -PathType Leaf)) {
    $workRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.edinburgh-study-agent\work'
}
if ((Split-Path $workRoot -Leaf) -eq 'work') { $studyRoot = Split-Path $workRoot -Parent }
elseif ((Split-Path (Split-Path $workRoot -Parent) -Leaf) -eq 'accounts') {
    $studyRoot = Split-Path (Split-Path (Split-Path $workRoot -Parent) -Parent) -Parent
} else { throw 'Unsupported UoE connection directory.' }
$python = Join-Path $studyRoot 'runtime\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'UoE runtime is missing.' }
$arguments = @('-m','edinburgh_study_agent.work_runtime','stop','--connection-directory',$workRoot)
if ($ConnectOnce) { $arguments += '--connect-once' }
& $python @arguments
exit $LASTEXITCODE
