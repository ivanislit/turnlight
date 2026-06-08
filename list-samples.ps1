param(
    [switch] $UserData
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$sampleRoot = if ($UserData) {
    Join-Path $env:LOCALAPPDATA "Turnlight\samples"
} else {
    Join-Path $PSScriptRoot "samples"
}

Write-Host "Samples: $sampleRoot"

$states = "busy_stop", "typing_arrow", "ignored"
foreach ($state in $states) {
    $dir = Join-Path $sampleRoot $state
    $count = 0
    if (Test-Path $dir) {
        $count = @(Get-ChildItem -Path $dir -Filter *.png -File).Count
    }
    Write-Host ("{0,-14} {1,3} samples" -f $state, $count)
}
