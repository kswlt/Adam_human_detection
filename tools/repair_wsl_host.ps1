[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Apply,
    [switch]$RestartWSL,
    [string]$Distro = 'Ubuntu'
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

function Set-IniKey {
    param([string]$Path, [string]$Section, [string]$Key, [string]$Value)
    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $Path) {
        Get-Content -LiteralPath $Path | ForEach-Object { [void]$lines.Add($_) }
    }
    $header = "[$Section]"
    $sectionStart = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim().Equals($header, [StringComparison]::OrdinalIgnoreCase)) { $sectionStart = $i; break }
    }
    if ($sectionStart -lt 0) {
        if ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -ne '') { [void]$lines.Add('') }
        [void]$lines.Add($header)
        [void]$lines.Add("$Key=$Value")
    } else {
        $sectionEnd = $lines.Count
        for ($i = $sectionStart + 1; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match '^\s*\[') { $sectionEnd = $i; break }
        }
        $keyIndex = -1
        for ($i = $sectionStart + 1; $i -lt $sectionEnd; $i++) {
            if ($lines[$i] -match ('^\s*' + [regex]::Escape($Key) + '\s*=')) { $keyIndex = $i; break }
        }
        if ($keyIndex -ge 0) { $lines[$keyIndex] = "$Key=$Value" } else { $lines.Insert($sectionEnd, "$Key=$Value") }
    }
    [System.IO.File]::WriteAllLines($Path, $lines, [System.Text.UTF8Encoding]::new($false))
}

function Backup-File([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $backup = "$Path.codex-backup-$stamp"
        Copy-Item -LiteralPath $Path -Destination $backup -Force
        return $backup
    }
    return $null
}

function Test-LocalEndpoint([int]$Port, [string]$Path) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port$Path" -UseBasicParsing -TimeoutSec 4
        return [ordered]@{ ok = $true; status = $response.StatusCode; body = $response.Content }
    } catch {
        return [ordered]@{ ok = $false; error = $_.Exception.Message }
    }
}

function Get-NvidiaSmi {
    $command = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if (-not $command) { $command = Get-Command nvidia-smi -ErrorAction SilentlyContinue }
    if (-not $command) { return @('nvidia-smi was not found on the Windows PATH') }
    return @(& $command.Source 2>&1)
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$wslConfig = Join-Path $env:USERPROFILE '.wslconfig'
$before = [ordered]@{
    admin = $isAdmin
    wsl_version = @(& wsl.exe --version 2>&1)
    wsl_status = @(& wsl.exe --status 2>&1)
    wslconfig = if (Test-Path $wslConfig) { Get-Content -LiteralPath $wslConfig } else { @() }
    gateway = Test-LocalEndpoint 8080 '/api/status'
    analytics = Test-LocalEndpoint 8090 '/api/analytics'
    nvidia_smi = Get-NvidiaSmi
}

if (-not $Apply) {
    [pscustomobject]@{ action = 'diagnose_only'; before = $before; hint = 'Run again with -Apply -RestartWSL from an elevated PowerShell only if WSL interop is still unavailable in a normal WSL terminal.' } | ConvertTo-Json -Depth 8
    exit 0
}

if (-not $isAdmin) { throw 'Run this script from an Administrator PowerShell when using -Apply.' }
if (-not $PSCmdlet.ShouldProcess('WSL user configuration', 'Enable interop and mirrored localhost access')) { exit 0 }

$available = @(& wsl.exe -l -q 2>&1 | Where-Object { $_ -and $_ -notmatch 'error' })
if ($available -notcontains $Distro) { $Distro = $available | Select-Object -First 1 }
if (-not $Distro) { throw 'No installed WSL distribution was found.' }
$wslConf = "\\wsl.localhost\$Distro\etc\wsl.conf"
if (-not (Test-Path -LiteralPath $wslConf)) { throw "Cannot access $wslConf. Start the distro once, then rerun this script." }

$hasMirroredNetworking = (Test-Path -LiteralPath $wslConfig) -and ((Get-Content -LiteralPath $wslConfig) -match '^\s*networkingMode\s*=\s*mirrored\s*$')
if (-not $hasMirroredNetworking) {
    $versionText = ($before.wsl_version -join "`n")
    if ($versionText -notmatch '(?im)^WSL version:\s*([0-9]+(?:\.[0-9]+){1,3})') {
        throw 'Unable to verify a WSL version that supports mirrored networking. Update WSL first; no configuration was changed.'
    }
    if ([version]$Matches[1] -lt [version]'2.0.9') {
        throw 'Installed WSL is older than 2.0.9, so mirrored networking was not enabled. Update WSL first; no configuration was changed.'
    }
}

$backups = @()
$backup = Backup-File $wslConfig
if ($backup) { $backups += $backup }
Set-IniKey -Path $wslConfig -Section 'wsl2' -Key 'networkingMode' -Value 'mirrored'

$temporaryWslConf = Join-Path $env:TEMP "codex-wsl-conf-$stamp"
Copy-Item -LiteralPath $wslConf -Destination $temporaryWslConf -Force
Set-IniKey -Path $temporaryWslConf -Section 'interop' -Key 'enabled' -Value 'true'
Set-IniKey -Path $temporaryWslConf -Section 'interop' -Key 'appendWindowsPath' -Value 'true'
$linuxBackup = "/etc/wsl.conf.codex-backup-$stamp"
& wsl.exe -d $Distro -u root -- cp /etc/wsl.conf $linuxBackup
$encodedWslConf = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($temporaryWslConf))
& wsl.exe -d $Distro -u root -- sh -lc "printf '%s' '$encodedWslConf' | base64 -d > /etc/wsl.conf"
Remove-Item -LiteralPath $temporaryWslConf -Force
$backups += "\\wsl.localhost\$Distro$linuxBackup"

if ($RestartWSL) { & wsl.exe --shutdown }
[pscustomobject]@{
    action = 'applied'
    distro = $Distro
    backups = $backups
    wslconfig = $wslConfig
    wsl_conf = $wslConf
    next = if ($RestartWSL) { 'Open a new WSL terminal, then run tools/dev_env_check.sh.' } else { 'Run wsl --shutdown, open a new WSL terminal, then run tools/dev_env_check.sh.' }
} | ConvertTo-Json -Depth 8
