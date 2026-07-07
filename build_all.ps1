# NDEX release builder - builds all four apps and assembles a portable release folder.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\build_all.ps1
#   powershell -ExecutionPolicy Bypass -File .\build_all.ps1 -SkipBuild   # assemble only

param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot

# Read version from ndex_common/version.py
$versionLine = Get-Content (Join-Path $repoRoot "ndex_common\version.py") | Where-Object { $_ -match 'NDEX_VERSION' }
$version = ($versionLine -split '"')[1]
if (-not $version) { $version = "0.0.0" }

Write-Host "== NDEX release build v$version =="

if (-not $SkipBuild) {
    Write-Host "[1/4] NDEX One"
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "build\build.ps1") -OneFile

    Write-Host "[2/4] NDEX Image Manager"
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "dsb_image_manager\build_package.ps1")

    Write-Host "[3/4] NDEX Auto Selector"
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "ndex_auto_selector\build_package.ps1")

    Write-Host "[4/4] NDEX Launcher"
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "ndex_launcher\build_package.ps1")
}

# Assemble portable release folder (all EXEs side by side so in-app handoff finds them)
$releaseDir = Join-Path $repoRoot "release\NDEX_v$version"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$artifacts = @(
    @{ Source = "dist\NDEX_One_OneFile.exe";                 Target = "NDEX_One_OneFile.exe" },
    @{ Source = "dsb_image_manager\dist\NDEX_Image_Manager.exe"; Target = "NDEX_Image_Manager.exe" },
    @{ Source = "ndex_auto_selector\dist\NDEX_Auto_Selector.exe"; Target = "NDEX_Auto_Selector.exe" },
    @{ Source = "ndex_launcher\dist\NDEX_Launcher.exe";      Target = "NDEX_Launcher.exe" }
)

$missing = @()
foreach ($artifact in $artifacts) {
    $sourcePath = Join-Path $repoRoot $artifact.Source
    if (Test-Path $sourcePath) {
        Copy-Item $sourcePath (Join-Path $releaseDir $artifact.Target) -Force
        Write-Host "  + $($artifact.Target)"
    } else {
        $missing += $artifact.Source
    }
}

# Bundle docs and third-party license notes
Copy-Item (Join-Path $repoRoot "release_README.md") (Join-Path $releaseDir "README.md") -Force
$exiftoolDir = Join-Path $repoRoot "vendor\exiftool"
if (Test-Path $exiftoolDir) {
    $licenseFiles = Get-ChildItem $exiftoolDir -Filter "*.txt" -ErrorAction SilentlyContinue
    if ($licenseFiles) {
        $thirdParty = Join-Path $releaseDir "third_party_licenses"
        New-Item -ItemType Directory -Force -Path $thirdParty | Out-Null
        $licenseFiles | Copy-Item -Destination $thirdParty -Force
    }
}

if ($missing.Count -gt 0) {
    Write-Warning "Missing artifacts (build them first): $($missing -join ', ')"
    exit 1
}

Write-Host "Release ready: $releaseDir"
