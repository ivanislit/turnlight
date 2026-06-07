$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = "0.9.0-beta"
$python = ".\.venv\Scripts\python.exe"
$pyInstaller = ".\.venv\Scripts\pyinstaller.exe"
$innoScript = ".\installer\turnlight.iss"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]] $Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

if (-not (Test-Path $python)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0 -and -not (Test-Path $python)) {
        throw "Could not create the virtual environment."
    }
}

if (-not (Test-Path ".\.venv\Scripts\pip.exe")) {
    Invoke-Checked $python -m ensurepip --upgrade --default-pip
}
Invoke-Checked $python -m pip install --disable-pip-version-check -r requirements.txt
Invoke-Checked $python -m pip install --disable-pip-version-check -r requirements-build.txt

Invoke-Checked $python .\prepare_assets.py

Remove-Item -LiteralPath ".\build\turnlight" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath ".\dist\Turnlight" -Recurse -Force -ErrorAction SilentlyContinue

Invoke-Checked $pyInstaller --noconfirm .\turnlight.spec

if (-not (Test-Path ".\dist\Turnlight\Turnlight.exe")) {
    throw "PyInstaller did not create dist\Turnlight\Turnlight.exe."
}

$isccCommand = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
$isccPath = if ($isccCommand) { $isccCommand.Source } else { $null }
if (-not $isccPath) {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            $isccPath = $candidate
            break
        }
    }
}

if ($isccPath) {
    New-Item -ItemType Directory -Force -Path ".\installer-output" | Out-Null
    Invoke-Checked $isccPath $innoScript
    if (-not (Test-Path ".\installer-output\Turnlight-$version-Setup.exe")) {
        throw "Inno Setup did not create the expected installer."
    }
    Write-Host "Installer created: installer-output\Turnlight-$version-Setup.exe" -ForegroundColor Green
} else {
    Write-Host "PyInstaller build created: dist\Turnlight\Turnlight.exe" -ForegroundColor Green
    Write-Host "Inno Setup was not found. Install Inno Setup 6, then rerun .\build.ps1 to create the installer." -ForegroundColor Yellow
}
