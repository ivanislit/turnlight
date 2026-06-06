$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0 -and -not (Test-Path ".\.venv\Scripts\python.exe")) {
        throw "Could not create the virtual environment."
    }
}

if (-not (Test-Path ".\.venv\Scripts\pip.exe")) {
    .\.venv\Scripts\python.exe -m ensurepip --upgrade --default-pip
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\prepare_assets.py

Write-Host ""
Write-Host "Turnlight installed. Run .\run.ps1 to start." -ForegroundColor Green
Write-Host "Recommended: run .\create-desktop-shortcut.ps1 to create a desktop shortcut." -ForegroundColor Cyan
