# NDEX release builder - builds all five apps and assembles a structured package.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\build_all.ps1
#   powershell -ExecutionPolicy Bypass -File .\build_all.ps1 -SkipBuild   # assemble only
#   powershell -ExecutionPolicy Bypass -File .\build_all.ps1 -Installer   # also compile NDEX_Setup_*.exe

param(
    [switch]$SkipBuild,
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot

# Read version from ndex_common/version.py
$versionLine = Get-Content (Join-Path $repoRoot "ndex_common\version.py") | Where-Object { $_ -match '^\s*NDEX_VERSION\s*=' }
$version = ($versionLine -split '"')[1]
if (-not $version) { throw "Could not read NDEX_VERSION from ndex_common\version.py" }

$releaseTag = $null
if ($env:GITHUB_REF_TYPE -eq "tag" -and $env:GITHUB_REF_NAME) {
    $releaseTag = $env:GITHUB_REF_NAME
} else {
    try {
        $releaseTag = git -C $repoRoot describe --tags --exact-match 2>$null
        if ($LASTEXITCODE -ne 0) { $releaseTag = $null }
    } catch {
        $releaseTag = $null
    }
}
if ($releaseTag) {
    $normalizedTag = $releaseTag
    if ($normalizedTag.StartsWith("v")) { $normalizedTag = $normalizedTag.Substring(1) }
    if ($normalizedTag -ne $version) {
        throw "Git tag '$releaseTag' does not match NDEX_VERSION '$version'."
    }
}

Write-Host "== NDEX release build v$version =="

if (-not $SkipBuild) {
    Write-Host "[1/5] NDEX One"
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "build\build.ps1") -OneFile

    Write-Host "[2/5] NDEX Image Manager"
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "dsb_image_manager\build_package.ps1")

    Write-Host "[3/5] NDEX Auto Selector"
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "ndex_auto_selector\build_package.ps1")

    Write-Host "[4/5] NDEX Frame"
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "ndex_frame\build_package.ps1")

    Write-Host "[5/5] NDEX Launcher"
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "ndex_launcher\build_package.ps1")
}

# Structured package: Launcher at root, workflow apps in Apps\, docs in Docs\
$releaseDir = Join-Path $repoRoot "release\NDEX_v$version"
$appsDir = Join-Path $releaseDir "Apps"
$docsDir = Join-Path $releaseDir "Docs"
New-Item -ItemType Directory -Force -Path $appsDir | Out-Null
New-Item -ItemType Directory -Force -Path $docsDir | Out-Null

$artifacts = @(
    @{ Source = "dist\NDEX_One_OneFile.exe"; Target = "Apps\NDEX_One.exe" },
    @{ Source = "dsb_image_manager\dist\NDEX_Image_Manager.exe"; Target = "Apps\NDEX_Image_Manager.exe" },
    @{ Source = "ndex_auto_selector\dist\NDEX_Auto_Selector.exe"; Target = "Apps\NDEX_Auto_Selector.exe" },
    @{ Source = "ndex_frame\dist\NDEX_Frame.exe"; Target = "Apps\NDEX_Frame.exe" },
    @{ Source = "ndex_launcher\dist\NDEX_Launcher.exe"; Target = "NDEX_Launcher.exe" }
)

$missing = @()
foreach ($artifact in $artifacts) {
    $sourcePath = Join-Path $repoRoot $artifact.Source
    $destPath = Join-Path $releaseDir $artifact.Target
    $destParent = Split-Path $destPath -Parent
    if (-not (Test-Path $destParent)) {
        New-Item -ItemType Directory -Force -Path $destParent | Out-Null
    }
    if (Test-Path $sourcePath) {
        Copy-Item $sourcePath $destPath -Force
        Write-Host "  + $($artifact.Target)"
    } else {
        $missing += $artifact.Source
    }
}

Copy-Item (Join-Path $repoRoot "README.md") (Join-Path $docsDir "README.md") -Force
$koreanReadme = Join-Path $repoRoot "README.ko.md"
if (Test-Path $koreanReadme) {
    Copy-Item $koreanReadme (Join-Path $docsDir "README.ko.md") -Force
}
foreach ($legal in @("LICENSE", "TERMS.md", "TERMS.ko.md")) {
    $legalPath = Join-Path $repoRoot $legal
    if (Test-Path $legalPath) {
        Copy-Item $legalPath (Join-Path $docsDir $legal) -Force
    }
}
$suiteNotes = Join-Path $repoRoot "PATCH_NOTES.md"
if (Test-Path $suiteNotes) {
    Copy-Item $suiteNotes (Join-Path $docsDir "PATCH_NOTES.md") -Force
}
$frameNotes = Join-Path $repoRoot "ndex_frame\PATCH_NOTES.md"
if (Test-Path $frameNotes) {
    Copy-Item $frameNotes (Join-Path $docsDir "FRAME_PATCH_NOTES.md") -Force
}
$notices = Join-Path $repoRoot "THIRD_PARTY_NOTICES.md"
if (Test-Path $notices) {
    Copy-Item $notices (Join-Path $docsDir "THIRD_PARTY_NOTICES.md") -Force
}
$exiftoolDir = Join-Path $repoRoot "vendor\exiftool"
if (Test-Path $exiftoolDir) {
    $licenseFiles = Get-ChildItem $exiftoolDir -Filter "*.txt" -ErrorAction SilentlyContinue
    if ($licenseFiles) {
        $thirdParty = Join-Path $docsDir "Licenses"
        New-Item -ItemType Directory -Force -Path $thirdParty | Out-Null
        $licenseFiles | Copy-Item -Destination $thirdParty -Force
    }
}

if ($missing.Count -gt 0) {
    Write-Warning "Missing artifacts (build them first): $($missing -join ', ')"
    exit 1
}

$sumsPath = Join-Path $releaseDir "SHA256SUMS.txt"
$sums = @()
Get-ChildItem -Path $releaseDir -Recurse -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" } | Sort-Object FullName | ForEach-Object {
    $hash = (Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLowerInvariant()
    $relative = $_.FullName.Substring($releaseDir.Length).TrimStart("\", "/") -replace "\\", "/"
    $sums += "$hash  $relative"
}
Set-Content -Path $sumsPath -Value $sums -Encoding ascii
Write-Host "  + SHA256SUMS.txt ($($sums.Count) files)"

if ($Installer) {
    $iscc = Get-Command ISCC -ErrorAction SilentlyContinue
    if (-not $iscc) {
        throw "Inno Setup (ISCC) is not installed. Install it, then rerun with -Installer."
    }
    Write-Host "Compiling suite installer"
    & $iscc.Source (Join-Path $repoRoot "build\installer.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Release ready: $releaseDir"
