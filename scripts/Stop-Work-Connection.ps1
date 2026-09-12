$ErrorActionPreference = 'Stop'
$studyRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.edinburgh-study-agent'
$workRoot = Join-Path $studyRoot 'work'
$taskName = 'Edinburgh Study Agent - Work connection'
$runner = Join-Path $workRoot 'Run-Work-Connection.ps1'
$powerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$settingsPath = Join-Path $workRoot 'connection.json'
$settings = $null
if (Test-Path -LiteralPath $settingsPath -PathType Leaf) {
    $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($settings.alias -ne 'edinburgh-study-agent') { throw 'Unexpected connection alias; nothing was stopped.' }
}
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    $existingActions = @($task.Actions)
    if ($existingActions.Count -ne 1 -or $existingActions[0].Execute -ine $powerShellExe -or -not $existingActions[0].Arguments.Contains('"' + $runner + '"')) {
        throw 'A different scheduled task uses the Edinburgh connection name; nothing was stopped.'
    }
    Disable-ScheduledTask -TaskName $taskName | Out-Null
    Stop-ScheduledTask -TaskName $taskName
}
if ($settings) {
    & $settings.client runtimes stop $settings.alias
    if ($LASTEXITCODE -ne 0) { throw 'Could not confirm the Edinburgh connection stopped.' }
}
Write-Output 'Edinburgh Work startup disabled and its managed runtime stopped. Course files and task data are preserved.'
