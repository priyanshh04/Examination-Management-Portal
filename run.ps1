$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create .venv. Install Python 3.11+ first.' }
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install Python dependencies.' }
}
& .\.venv\Scripts\python.exe --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Remove-Item -Recurse -Force .venv
    py -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'The existing Python environment is invalid and Python could not recreate it.' }
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install Python dependencies.' }
}
& .\.venv\Scripts\python.exe app.py
