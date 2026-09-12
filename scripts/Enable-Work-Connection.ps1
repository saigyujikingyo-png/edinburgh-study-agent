$ErrorActionPreference = 'Stop'
$studyRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.edinburgh-study-agent'
$workRoot = Join-Path $studyRoot 'work'
$runner = Join-Path $workRoot 'Run-Work-Connection.ps1'
if (-not (Test-Path -LiteralPath $runner -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $workRoot 'connection.json') -PathType Leaf)) {
    throw 'Prepare the authorized Edinburgh Work connection first.'
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskName = 'Edinburgh Study Agent - Work connection'
$powerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runner + '"'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    $existingActions = @($existing.Actions)
    if ($existingActions.Count -ne 1 -or $existingActions[0].Execute -ine $powerShellExe -or -not $existingActions[0].Arguments.Contains('"' + $runner + '"')) {
        throw 'A different scheduled task already uses the Edinburgh connection name.'
    }
}
$action = New-ScheduledTaskAction -Execute $powerShellExe -Argument $arguments -WorkingDirectory $workRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Private Edinburgh coursework connection for the current personal ChatGPT Work workspace.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
