# NDEX Frame one-file Windows build.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\ndex_frame\build_package.ps1

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$appRoot = Resolve-Path $PSScriptRoot
$buildTools = Join-Path $repoRoot ".build_tools"
$distPath = Join-Path $appRoot "dist"
$workPath = Join-Path $appRoot "build"
$entryPoint = Join-Path $appRoot "main.py"
$versionFile = Join-Path $workPath "NDEX_Frame_version.txt"

$env:PYTHONPATH = "$buildTools;$env:PYTHONPATH"

$versionLine = Get-Content (Join-Path $repoRoot "ndex_common\version.py") | Where-Object { $_ -match "NDEX_VERSION" }
$version = ($versionLine -split '"')[1]
if (-not $version) { $version = "0.0.0" }
$parts = @($version.Split("."))
while ($parts.Count -lt 4) { $parts += "0" }
$v1 = [int]$parts[0]
$v2 = [int]$parts[1]
$v3 = [int]$parts[2]
$v4 = [int]$parts[3]

python -m pip install "pyinstaller==6.11.1"

New-Item -ItemType Directory -Force -Path $distPath, $workPath | Out-Null

$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($v1, $v2, $v3, $v4),
    prodvers=($v1, $v2, $v3, $v4),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'NDEX'),
        StringStruct(u'FileDescription', u'NDEX Frame - photography framing and export'),
        StringStruct(u'FileVersion', u'$version'),
        StringStruct(u'InternalName', u'NDEX_Frame'),
        StringStruct(u'OriginalFilename', u'NDEX_Frame.exe'),
        StringStruct(u'ProductName', u'NDEX Frame'),
        StringStruct(u'ProductVersion', u'$version')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($versionFile, $versionInfo, $utf8)

python -m PyInstaller `
  --noconfirm --clean --onefile --windowed `
  --name NDEX_Frame `
  --paths $appRoot --paths $repoRoot `
  --collect-submodules ndex_frame `
  --collect-submodules ndex_common `
  --collect-all PySide6 `
  --hidden-import PIL.ImageCms `
  --add-data "$repoRoot\assets\branding;assets\branding" `
  --add-data "$appRoot\resources;ndex_frame\resources" `
  --icon "$repoRoot\assets\branding\ndex_icon.ico" `
  --version-file $versionFile `
  --distpath $distPath `
  --workpath $workPath `
  --specpath $workPath `
  $entryPoint

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$built = Join-Path $distPath "NDEX_Frame.exe"
if (-not (Test-Path $built)) {
    throw "Expected packaged executable was not created: $built"
}

Write-Host "Built $built"
