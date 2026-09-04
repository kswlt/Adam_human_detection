$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv_ai\Scripts\python.exe'
Write-Host '=== nvidia-smi ==='
nvidia-smi
Write-Host '=== Python / ORT / Torch ==='
& $python -c "import sys,onnxruntime as ort,torch; print('python',sys.version); print('executable',sys.executable); print('ORT',ort.__version__); print('providers',ort.get_available_providers()); print('ORT device',ort.get_device()); print('torch',torch.__version__); print('torch CUDA',torch.version.cuda); print('torch.cuda.is_available',torch.cuda.is_available()); print('GPU',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
Write-Host '=== installed ORT distributions ==='
& $python -m pip show onnxruntime onnxruntime-gpu
Write-Host '=== CUDA DLLs in AI environment ==='
Get-ChildItem (Join-Path $root '.venv_ai\Lib\site-packages\nvidia') -Recurse -Filter '*.dll' | Select-Object -ExpandProperty FullName
