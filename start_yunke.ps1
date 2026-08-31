# One local gateway, supervised without resetting the NIC or restarting board services.
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $dir '.venv\Scripts\python.exe'
$runtime = Join-Path $dir 'runtime'
$config = Get-Content -LiteralPath (Join-Path $dir 'config\pc.json') -Raw | ConvertFrom-Json
$healthUrl = "http://127.0.0.1:$($config.http_port)/api/status"
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$mutex = New-Object System.Threading.Mutex($false, 'Global\YunkePcGatewaySupervisor')
if (-not $mutex.WaitOne(0)) { exit 0 }
$child = $null
try {
    if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup_pc.ps1 first.' }
    while ($true) {
        $child = Start-Process -FilePath $python -ArgumentList '-m', 'pc.gateway' `
            -WorkingDirectory $dir -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $runtime 'gateway.stdout.log') `
            -RedirectStandardError (Join-Path $runtime 'gateway.stderr.log')
        $failures = 0
        while (-not $child.WaitForExit(2000)) {
            try {
                $null = Invoke-RestMethod $healthUrl -TimeoutSec 2
                $failures = 0
            } catch {
                $failures++
                if ($failures -ge 5) {
                    # Windows venv python.exe may spawn a redirector child.
                    & taskkill.exe /PID $child.Id /T /F 2>$null | Out-Null
                    break
                }
            }
        }
        "$(Get-Date -Format o) gateway exited; restart in 1s" |
            Out-File (Join-Path $runtime 'supervisor.log') -Append -Encoding utf8
        Start-Sleep -Seconds 1
    }
} finally {
    if ($child -and -not $child.HasExited) { & taskkill.exe /PID $child.Id /T /F 2>$null | Out-Null }
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
