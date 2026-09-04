$ErrorActionPreference='Stop'
$dir=Split-Path -Parent $MyInvocation.MyCommand.Path
$models=Join-Path $dir '..\models'
New-Item -ItemType Directory -Force $models | Out-Null
Write-Host 'Model downloads are intentionally explicit. Install .venv_ai first.'
Write-Host 'Ultralytics will download the configured YOLO model on first load; InsightFace buffalo_l downloads its model pack on first load.'
Write-Host 'For production, pin and record SHA256 for each model in models/README.md before deployment.'

