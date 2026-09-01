param(
    [switch]$Installer,
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SpecPath = Join-Path $ProjectRoot "build\NDEX_One.spec"
$OneFileSpecPath = Join-Path $ProjectRoot "build\NDEX_One.onefile.spec"
$VendorExifTool = Join-Path $ProjectRoot "vendor\exiftool\exiftool.exe"

Write-Host "Project root: $ProjectRoot"

if (-not (Test-Path $VendorExifTool)) {
    Write-Warning "ExifTool not found at $VendorExifTool"
    Write-Warning "The build will continue, but CR3 metadata extraction in the packaged app will fall back if ExifTool is missing."
}

python -m pip install --upgrade "pyinstaller==6.11.1"
if ($OneFile) {
    python -m PyInstaller --noconfirm --clean $OneFileSpecPath
}
else {
    python -m PyInstaller --noconfirm --clean $SpecPath
}

if ($Installer) {
    $Iscc = Get-Command ISCC -ErrorAction SilentlyContinue
    if (-not $Iscc) {
        throw "Inno Setup (ISCC) is not installed. Install it first, then rerun with -Installer."
    }

    & $Iscc.Source (Join-Path $ProjectRoot "build\installer.iss")
}

Write-Host "Build completed."
