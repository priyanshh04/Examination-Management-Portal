$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$cache = Join-Path ([System.IO.Path]::GetTempPath()) 'emp-pycache'
New-Item -ItemType Directory -Force $cache | Out-Null
$env:PYTHONPYCACHEPREFIX = $cache
$python = $null
if (Test-Path '.venv\Scripts\python.exe') { $python = (Resolve-Path '.venv\Scripts\python.exe').Path }
if (-not $python) {
    $candidate = (Get-Command py -ErrorAction SilentlyContinue)
    if ($candidate) { $python = 'py' }
}
if (-not $python) { throw 'Python was not found. Install Python 3.11+ and recreate .venv.' }
& $python --version
if ($LASTEXITCODE -ne 0) { throw 'Python was found but could not start. Reinstall Python and recreate .venv.' }
& $python -m py_compile app.py app_factory.py config.py database\db.py backend\cache.py tasks\celery_app.py tasks\scheduled_tasks.py
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }
& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed.' }
Write-Host 'EMP verification passed.' -ForegroundColor Green
