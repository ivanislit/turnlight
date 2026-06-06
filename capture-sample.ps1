$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($args.Count -ne 1) {
    Write-Host "Usage: .\capture-sample.ps1 <state>" -ForegroundColor Yellow
    Write-Host "States: busy_stop, typing_arrow, ignored"
    exit 2
}

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Missing virtual environment. Run .\install.ps1 first." -ForegroundColor Yellow
    exit 1
}

& $python .\capture_sample.py $args[0]
