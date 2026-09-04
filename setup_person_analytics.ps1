$ErrorActionPreference='Stop'
$dir=Split-Path -Parent $MyInvocation.MyCommand.Path
if(-not(Test-Path (Join-Path $dir '.venv_ai\Scripts\python.exe'))){ py -3.11 -m venv (Join-Path $dir '.venv_ai') }
& (Join-Path $dir '.venv_ai\Scripts\python.exe') -m pip install -r (Join-Path $dir 'requirements-ai.txt')
# InsightFace declares the CPU distribution as a dependency; enforce the GPU
# distribution as the final ORT package in this isolated environment.
& (Join-Path $dir '.venv_ai\Scripts\python.exe') -m pip uninstall -y onnxruntime
& (Join-Path $dir '.venv_ai\Scripts\python.exe') -m pip install --upgrade "onnxruntime-gpu[cuda,cudnn]==1.29.0"
& (Join-Path $dir '.venv_ai\Scripts\python.exe') -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu130 torch torchvision
