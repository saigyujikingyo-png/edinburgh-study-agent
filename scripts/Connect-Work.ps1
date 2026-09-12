param(
    [Parameter(Mandatory=$true)][string]$TunnelId,
    [Parameter(Mandatory=$true)][string]$TunnelClient,
    [string]$KeyEnvironmentVariable = 'EDINBURGH_TUNNEL_KEY'
)
$ErrorActionPreference = 'Stop'
if ($TunnelId -notmatch '^tunnel_[a-f0-9]+$') { throw 'Use the real tunnel ID from OpenAI Platform.' }
if ($KeyEnvironmentVariable -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { throw 'Invalid key environment variable name.' }
if (-not (Test-Path -LiteralPath $TunnelClient -PathType Leaf)) { throw 'Install the official tunnel-client first.' }
$studyRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.edinburgh-study-agent'
$runtimePython = Join-Path $studyRoot 'runtime\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) { throw 'Install the Edinburgh Study Agent runtime first.' }
$workRoot = Join-Path $studyRoot 'work'
$secretRoot = Join-Path $studyRoot 'secrets'
$secretFile = Join-Path $secretRoot 'work-tunnel-key.dpapi'
$keyText = [Environment]::GetEnvironmentVariable($KeyEnvironmentVariable, 'Process')
if (-not $keyText -and -not (Test-Path -LiteralPath $secretFile -PathType Leaf)) {
    throw 'Provide your tunnel runtime key locally in the selected environment variable. Never put it in chat.'
}
New-Item -ItemType Directory -Path $workRoot,$secretRoot -Force | Out-Null
$settingsPath = Join-Path $workRoot 'connection.json'
if (Test-Path -LiteralPath $settingsPath) {
    $existing = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($existing.tunnel_id -ne $TunnelId) { throw 'A different Edinburgh tunnel is configured. Review it before replacing its identity.' }
}
if ($keyText) {
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
    alias = 'edinburgh-study-agent'
    tunnel_id = $TunnelId
    client = $localClient
    python = $runtimePython
    module = 'edinburgh_study_agent.server'
    profile_directory = (Join-Path $workRoot 'profiles')
}
[IO.File]::WriteAllText($settingsPath, ($settings | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
foreach ($scriptName in @('Run-Work-Connection.ps1','Enable-Work-Connection.ps1','Stop-Work-Connection.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $scriptName) -Destination (Join-Path $workRoot $scriptName) -Force
}
Write-Output 'Edinburgh private connection prepared. Start Run-Work-Connection.ps1 to connect, or enable its login task after authorizing persistent Work access.'
