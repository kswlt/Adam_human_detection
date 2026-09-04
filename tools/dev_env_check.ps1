[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

function Get-ListenerInfo([int]$Port) {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
        [pscustomobject]@{
            port = $Port
            local_address = $listener.LocalAddress
            pid = $listener.OwningProcess
            process = if ($process) { $process.ProcessName } else { $null }
        }
    }
}

function Get-JsonEndpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        [pscustomobject]@{ ok = $true; status_code = $response.StatusCode; body = ($response.Content | ConvertFrom-Json) }
    } catch {
        $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { $null }
        [pscustomobject]@{ ok = $false; status_code = $status; error = $_.Exception.Message }
    }
}

$result = [ordered]@{
    checked_at = (Get-Date).ToString('o')
    windows_interop = $true
    gateway_8080 = [ordered]@{ listeners = @(Get-ListenerInfo 8080); status = Get-JsonEndpoint 'http://127.0.0.1:8080/api/status' }
    analytics_8090 = [ordered]@{ listeners = @(Get-ListenerInfo 8090); status = Get-JsonEndpoint 'http://127.0.0.1:8090/api/analytics' }
}

try {
    $image = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/latest.jpg' -UseBasicParsing -TimeoutSec 5
    $result.gateway_8080.latest_jpg = [ordered]@{ ok = $true; status_code = $image.StatusCode; bytes = $image.Content.Length; content_type = $image.Headers['Content-Type'] }
} catch {
    $result.gateway_8080.latest_jpg = [ordered]@{ ok = $false; error = $_.Exception.Message }
}

$nvidia = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if (-not $nvidia) { $nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue }
try {
    $result.gpu = if ($nvidia) {
        [ordered]@{ ok = $true; executable = $nvidia.Source; query = @(& $nvidia.Source '--query-gpu=name,driver_version,cuda_version,memory.used,memory.total,utilization.gpu' '--format=csv,noheader,nounits' 2>&1) }
    } else {
        [ordered]@{ ok = $false; error = 'nvidia-smi was not found on the Windows PATH' }
    }
} catch {
    $result.gpu = [ordered]@{ ok = $false; error = $_.Exception.Message }
}

$python = Join-Path $ProjectRoot '.venv_ai\Scripts\python.exe'
if (Test-Path -LiteralPath $python) {
    $probe = @'
import json
import onnxruntime as ort
import torch
print(json.dumps({
    "python": __import__("sys").version,
    "torch_cuda_available": torch.cuda.is_available(),
    "torch_cuda": torch.version.cuda,
    "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "onnxruntime": ort.__version__,
    "providers": ort.get_available_providers(),
}))
'@
    try {
        $result.windows_python = [ordered]@{ ok = $true; executable = $python; probe = ((& $python -c $probe 2>&1) -join "`n") }
    } catch {
        $result.windows_python = [ordered]@{ ok = $false; executable = $python; error = $_.Exception.Message }
    }
} else {
    $result.windows_python = [ordered]@{ ok = $false; error = "Missing virtual environment: $python" }
}

if ($result.gateway_8080.status.ok) {
    $image = $result.gateway_8080.status.body.image
    $result.camera = [ordered]@{ healthy = $image.healthy; hz = $image.hz; age_seconds = $image.age_seconds; last_error = $image.last_error }
}
if ($result.analytics_8090.status.ok) {
    $ai = $result.analytics_8090.status.body
    $result.analytics = [ordered]@{ camera_fps = $ai.camera_fps; ai_fps = $ai.ai_fps; face_fps = $ai.face_fps; latency_ms = $ai.latency_ms; detector_device = $ai.detector_device; insightface_provider = $ai.insightface_provider; input = $ai.input; face_diagnostics = $ai.face_diagnostics }
}

$result | ConvertTo-Json -Depth 10
