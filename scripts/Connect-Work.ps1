param(
    [Parameter(Mandatory=$true)][string]$TunnelId,
    [Parameter(Mandatory=$true)][string]$TunnelClient,
    [string]$KeyEnvironmentVariable = 'EDINBURGH_TUNNEL_KEY',
    [ValidatePattern('^(primary|[a-z][a-z0-9-]{2,40})$')][string]$Account = 'primary',
    [ValidatePattern('^[a-z][a-z0-9-]{2,63}$')][string]$Alias,
    [string]$TaskName
)
$ErrorActionPreference = 'Stop'
if ($TunnelId -notmatch '^tunnel_[a-f0-9]+$') { throw 'Use the real tunnel ID from OpenAI Platform.' }
if ($KeyEnvironmentVariable -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { throw 'Invalid key environment variable name.' }
if (-not (Test-Path -LiteralPath $TunnelClient -PathType Leaf)) { throw 'Install the official tunnel-client first.' }
$studyRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.edinburgh-study-agent'
$runtimePython = Join-Path $studyRoot 'runtime\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) { throw 'Install the UoE Companion runtime first.' }
$workRoot = Join-Path $studyRoot 'work'
$secretRoot = Join-Path $studyRoot 'secrets'
$secretName = 'work-tunnel-key.dpapi'
if ($Account -ne 'primary') {
    $workRoot = Join-Path $workRoot ('accounts\'+$Account)
    $secretName = 'work-'+$Account+'-key.dpapi'
}
if (-not $Alias) {
    if ($Account -eq 'primary') { $Alias = 'edinburgh-study-agent' }
    elseif ($Account -eq 'school-chatgpt') { $Alias = 'uoe-companion-school' }
    else { $Alias = 'uoe-'+$Account }
}
if (-not $TaskName) {
    if ($Account -eq 'primary') { $TaskName = 'Edinburgh Study Agent - Work connection' }
    elseif ($Account -eq 'school-chatgpt') { $TaskName = 'UoE Companion - School account connection' }
    else { $TaskName = 'UoE Companion - '+$Account+' connection' }
}
if ($TaskName.Length -gt 160 -or $TaskName -match '[\\/\x00-\x1f*?\[\]]') { throw 'Invalid account task name.' }
$secretFile = Join-Path $secretRoot $secretName
$keyText = [Environment]::GetEnvironmentVariable($KeyEnvironmentVariable, 'Process')
if (-not $keyText -and -not (Test-Path -LiteralPath $secretFile -PathType Leaf)) {
    throw 'Provide your tunnel runtime key locally in the selected environment variable. Never put it in chat.'
}
New-Item -ItemType Directory -Path $workRoot,$secretRoot -Force | Out-Null
$settingsPath = Join-Path $workRoot 'connection.json'
if (Test-Path -LiteralPath $settingsPath) {
    $existing = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($existing.tunnel_id -ne $TunnelId -or $existing.alias -ne $Alias) { throw 'A different Edinburgh tunnel is configured. Review it before replacing its identity.' }
}
if ($keyText -and -not (Test-Path -LiteralPath $secretFile -PathType Leaf)) {
    if ($keyText.Trim() -notmatch '^sk-') { throw 'Expected an OpenAI tunnel runtime key.' }
    $secureKey = ConvertTo-SecureString $keyText.Trim() -AsPlainText -Force
    try {
        $protectedText = ConvertFrom-SecureString $secureKey
        [IO.File]::WriteAllText($secretFile, $protectedText, [Text.UTF8Encoding]::new($false))
    } finally {
        $secureKey.Dispose()
        $keyText = $null
    }
}
$clientRoot = Join-Path $workRoot 'bin'
New-Item -ItemType Directory -Path $clientRoot -Force | Out-Null
$localClient = Join-Path $clientRoot 'tunnel-client.exe'
$sourceClient = (Resolve-Path -LiteralPath $TunnelClient).Path
if ($sourceClient -ne $localClient) {
    if (Test-Path -LiteralPath $localClient) {
        if ((Get-FileHash -LiteralPath $localClient).Hash -ne (Get-FileHash -LiteralPath $sourceClient).Hash) {
            throw 'A different tunnel-client is already staged. Review the executable before replacing it.'
        }
    } else {
        Copy-Item -LiteralPath $sourceClient -Destination $localClient
    }
}
$settings = [ordered]@{
    alias = $Alias
    tunnel_id = $TunnelId
    client = $localClient
    python = $runtimePython
    module = 'edinburgh_study_agent.server'
    profile_directory = (Join-Path $workRoot 'profiles')
}
if (-not (Test-Path -LiteralPath $settingsPath -PathType Leaf)) {
    [IO.File]::WriteAllText($settingsPath, ($settings | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
}
# The installed release owns all profile launchers. Never hand-patch the school
# account or rewrite its app, tunnel or credential identity during reconfiguration.
& $runtimePython -m edinburgh_study_agent.work_profiles prepare --connection-directory $workRoot --alias $Alias --task-name $TaskName --secret-file ('secrets/'+$secretName)
if ($LASTEXITCODE -ne 0) { throw 'The existing account was preserved; launcher preparation needs review.' }
Write-Output 'Edinburgh private connection prepared. Start Run-Work-Connection.ps1 to connect, or enable its login task after authorizing persistent Work access.'
