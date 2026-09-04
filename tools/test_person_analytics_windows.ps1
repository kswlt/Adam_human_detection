$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv_ai\Scripts\python.exe'
Write-Host '=== GPU / CUDA / Python / ORT ==='
nvidia-smi
& $python -c "import sys,onnxruntime as ort; ort.preload_dlls(); import torch; print('Python',sys.version); print('Executable',sys.executable); print('ORT',ort.__version__); print('Providers',ort.get_available_providers()); print('ORT device',ort.get_device()); print('Torch',torch.__version__); print('Torch CUDA',torch.version.cuda); print('CUDA available',torch.cuda.is_available()); print('GPU',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
Write-Host '=== ORT distributions ==='
& $python -m pip show onnxruntime onnxruntime-gpu
Write-Host '=== Compile ==='
& $python -m compileall -q (Join-Path $root 'pc\person_analytics')
Write-Host '=== AI service status ==='
try { (Invoke-WebRequest 'http://127.0.0.1:8090/api/analytics' -UseBasicParsing -TimeoutSec 10).Content } catch { Write-Host $_.Exception.Message }
Write-Host '=== Gateway status ==='
try { (Invoke-WebRequest 'http://127.0.0.1:8080/api/status' -UseBasicParsing -TimeoutSec 10).Content } catch { Write-Host $_.Exception.Message }
Write-Host '=== Optional image benchmark ==='
$image = Join-Path $root 'runtime\benchmark.jpg'
if (Test-Path $image) { & $python (Join-Path $root 'scripts\benchmark_ai_gpu.py') $image --sizes 640,960,1280 --runs 20 }
else { Write-Host "Put a representative JPEG at $image to run YOLO/face/ArcFace latency benchmark." }
