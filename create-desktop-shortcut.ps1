$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$desktop = [Environment]::GetFolderPath("DesktopDirectory")
$shortcutPath = Join-Path $desktop "Turnlight.lnk"
$target = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
$script = Join-Path $PSScriptRoot "turnlight.py"
$icon = Join-Path $PSScriptRoot "assets\app\turnlight.ico"

if (-not (Test-Path $target)) {
    throw "Missing $target. Run .\install.ps1 first."
}

if (-not (Test-Path $icon)) {
    & .\.venv\Scripts\python.exe .\prepare_assets.py
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.Arguments = "`"$script`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.WindowStyle = 1
$shortcut.Description = "Turnlight"
if (Test-Path $icon) {
    $shortcut.IconLocation = $icon
}
$shortcut.Save()

Write-Host "Desktop shortcut created: $shortcutPath" -ForegroundColor Green
