param([switch]$ConnectOnce)
$ErrorActionPreference = 'Stop'
$studyRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.edinburgh-study-agent'
$workRoot = Join-Path $studyRoot 'work'
$settingsPath = Join-Path $workRoot 'connection.json'
$secretFile = Join-Path $studyRoot 'secrets\work-tunnel-key.dpapi'
$mutex = New-Object Threading.Mutex($false, ('Local\EdinburghStudyWork-' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value))
$ownsMutex = $false
$exitCode = 0
try {
    try { $ownsMutex = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { exit 0 }
    $retryDelays = @(5,15,30)
    $failures = 0
    while ($true) {
        $secureKey = $null
        $connectStarted = $false
        $priorControlKey = [Environment]::GetEnvironmentVariable('CONTROL_PLANE_API_KEY','Process')
        $priorUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8','Process')
        try {
            $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($settings.alias -ne 'edinburgh-study-agent' -or $settings.tunnel_id -notmatch '^tunnel_[a-f0-9]+$') { throw 'Invalid Edinburgh connection identity.' }
            if (-not (Test-Path -LiteralPath $settings.python -PathType Leaf) -or -not (Test-Path -LiteralPath $settings.client -PathType Leaf)) { throw 'Connection runtime is missing.' }
            $secureKey = ConvertTo-SecureString ([IO.File]::ReadAllText($secretFile).Trim())
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
            try { $runtimeKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim() }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
            if ($runtimeKey -notmatch '^sk-') { throw 'The local tunnel key is invalid.' }
            [Environment]::SetEnvironmentVariable('CONTROL_PLANE_API_KEY',$runtimeKey,'Process')
            [Environment]::SetEnvironmentVariable('PYTHONUTF8','1','Process')
            $runtimeKey = $null
            $mcpCommand = '"' + $settings.python.Replace('\','/') + '" -m edinburgh_study_agent.server'
            $connectStarted = $true
            $connectOutput = & $settings.client runtimes connect --json --alias $settings.alias --profile $settings.alias --profile-dir $settings.profile_directory --tunnel-id $settings.tunnel_id --mcp-command $mcpCommand --runtime-api-key env:CONTROL_PLANE_API_KEY 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'The private tunnel connection failed. Check the authorized identity and runtime-key permissions.' }
            # Connection creation can finish before the MCP child becomes ready.
            # Poll that same daemon; immediately reconnecting leaks duplicate workers.
            $status = $null
            for ($readyAttempt = 0; $readyAttempt -lt 20; $readyAttempt++) {
                $statusOutput = & $settings.client runtimes status $settings.alias --json 2>&1
                if ($LASTEXITCODE -eq 0) { $status = ($statusOutput -join [Environment]::NewLine) | ConvertFrom-Json }
                if ($status -and $status.process_running -and $status.healthy -and $status.ready) { break }
                Start-Sleep -Seconds 1
            }
            if (-not $status -or -not $status.process_running -or -not $status.healthy -or -not $status.ready) {
                throw 'The private connection did not become ready.'
            }
            [Environment]::SetEnvironmentVariable('CONTROL_PLANE_API_KEY',$priorControlKey,'Process')
            [Environment]::SetEnvironmentVariable('PYTHONUTF8',$priorUtf8,'Process')
            $secureKey.Dispose()
            $secureKey = $null
            $tunnelProcess = Get-Process -Id $status.process.pid -ErrorAction Stop
            $startedAt = $tunnelProcess.StartTime
            $readyAt = [DateTime]::UtcNow
            $receipt = [ordered]@{
                checked_at = $readyAt.ToString('o')
                alias = $settings.alias
                process_running = $true
                healthy = [bool]$status.healthy
                ready = [bool]$status.ready
                pid = $tunnelProcess.Id
                recovery_attempt = $failures
                verification_scope = 'transport_only'
                supervisor_pid = $PID
            }
            [IO.File]::WriteAllText((Join-Path $workRoot 'status.json'), ($receipt | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
            if ($ConnectOnce) { $receipt | ConvertTo-Json; break }
            while ($true) {
                Start-Sleep -Seconds 30
                $current = Get-Process -Id $tunnelProcess.Id -ErrorAction SilentlyContinue
                if (-not $current -or $current.StartTime -ne $startedAt) { throw 'The private connection process stopped.' }
                if (([DateTime]::UtcNow - $readyAt).TotalSeconds -ge 300) { $failures = 0 }
            }
        } catch {
            # The client can spawn a daemon before connect itself fails. Clean the
            # exact owned profile even when the registry has no successful entry.
            if ($connectStarted) {
                $aliasPattern = '(?i)(?:^|\s)--profile\s+"?' + [regex]::Escape($settings.alias) + '"?(?=\s|$)'
                $directoryPattern = '(?i)(?:^|\s)--profile-dir\s+"?' + [regex]::Escape($settings.profile_directory) + '"?(?=\s|$)'
                $snapshot = @(Get-CimInstance Win32_Process)
                $owned = @($snapshot | Where-Object {
                    $_.ExecutablePath -ieq $settings.client -and
                    $_.CommandLine -match $aliasPattern -and $_.CommandLine -match $directoryPattern
                })
                $children = @($snapshot | Where-Object {
                    $_.ParentProcessId -in @($owned.ProcessId) -and
                    $_.ExecutablePath -ieq $settings.python -and
                    $_.CommandLine -match '(?:^|\s)-m\s+edinburgh_study_agent\.server(?:\s|$)'
                })
                try { $stopOutput = & $settings.client runtimes stop $settings.alias 2>&1 } catch { $stopOutput = $null }
                foreach ($candidate in @($owned) + @($children)) {
                    $current = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $candidate.ProcessId)
                    if ($current -and $current.CreationDate -eq $candidate.CreationDate -and $current.ExecutablePath -ieq $candidate.ExecutablePath) {
                        Stop-Process -Id $candidate.ProcessId -ErrorAction Stop
                    }
                }
            }
            $failures += 1
            $delay = if ($failures -le $retryDelays.Count -and -not $ConnectOnce) { $retryDelays[$failures-1] } else { 0 }
            $failure = [ordered]@{
                failed_at = [DateTime]::UtcNow.ToString('o')
                ready = $false
                consecutive_failures = $failures
                retry_seconds = $delay
                error = 'Edinburgh Work connection is unavailable. Inspect local runtime, tunnel association and key permissions.'
            }
            [IO.File]::WriteAllText((Join-Path $workRoot 'error.json'), ($failure | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
            if ($delay -eq 0) { throw }
            Start-Sleep -Seconds $delay
        } finally {
            [Environment]::SetEnvironmentVariable('CONTROL_PLANE_API_KEY',$priorControlKey,'Process')
            [Environment]::SetEnvironmentVariable('PYTHONUTF8',$priorUtf8,'Process')
            if ($secureKey) { $secureKey.Dispose() }
            $runtimeKey = $null
            $connectOutput = $null
            $statusOutput = $null
        }
    }
} catch {
    Write-Error 'Edinburgh Work connection did not start. No credential or control-plane response is printed.'
    $exitCode = 1
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
exit $exitCode
