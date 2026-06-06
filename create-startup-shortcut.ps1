$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Turnlight.lnk"
$target = (Get-Command pwsh.exe).Source
$runScript = Join-Path $PSScriptRoot "run.ps1"
$icon = Join-Path $PSScriptRoot "assets\app\turnlight.ico"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$runScript`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.WindowStyle = 7
$shortcut.Description = "Turnlight"
if (Test-Path $icon) {
    $shortcut.IconLocation = $icon
}
$shortcut.Save()

Write-Host "Startup shortcut created: $shortcutPath" -ForegroundColor Green
