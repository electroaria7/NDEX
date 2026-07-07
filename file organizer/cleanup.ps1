# NDEX cleanup script - removes generated artifacts, keeps source files.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\cleanup.ps1            # caches only
#   powershell -ExecutionPolicy Bypass -File .\cleanup.ps1 -IncludeDist  # also removes dist/ exe output

param(
    [switch]$IncludeDist
)

$root = $PSScriptRoot

Write-Host "Cleaning caches under $root"

Get-ChildItem -Path $root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

Get-ChildItem -Path $root -Recurse -File -Include "*.pyc", "*.pyo", "*.ndex_tmp" -ErrorAction SilentlyContinue |
    Remove-Item -Force

foreach ($dir in @("build\DSB", "build\DSB.onefile", ".dsb_data", "scratch")) {
    $path = Join-Path $root $dir
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
        Write-Host "Removed $dir"
    }
}

Get-ChildItem -Path $root -Directory -Filter "tmp_*" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

if ($IncludeDist) {
    foreach ($dir in @("dist", "dsb_image_manager\dist", "ndex_auto_selector\dist", "ndex_launcher\dist")) {
        $path = Join-Path $root $dir
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
            Write-Host "Removed $dir"
        }
    }
}

Write-Host "Cleanup completed."
