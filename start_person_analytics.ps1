$ErrorActionPreference='Stop'; $dir=Split-Path -Parent $MyInvocation.MyCommand.Path
$python=Join-Path $dir '.venv_ai\Scripts\python.exe'
if(-not(Test-Path $python)){ throw 'Run setup_person_analytics.ps1 first.' }
Push-Location $dir; try { & $python -m pc.person_analytics.app --source gateway } finally { Pop-Location }

