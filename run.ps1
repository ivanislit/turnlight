$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = ".\.venv\Scripts\pythonw.exe"
$script = Join-Path $PSScriptRoot "turnlight.py"

if (-not (Test-Path $python)) {
    Write-Host "Missing virtual environment. Run first: .\install.ps1" -ForegroundColor Yellow
    exit 1
}

.\.venv\Scripts\python.exe .\prepare_assets.py
Start-Process -FilePath $python -ArgumentList "`"$script`"" -WorkingDirectory $PSScriptRoot
