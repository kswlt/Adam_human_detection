$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv_ai\Scripts\python.exe'
if (!(Test-Path $py)) { throw "Missing AI environment: $py" }
& $py (Join-Path $PSScriptRoot 'validate_reid.py')
