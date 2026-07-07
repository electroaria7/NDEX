$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$appRoot = Resolve-Path $PSScriptRoot
$buildTools = Join-Path $repoRoot ".build_tools"
$distPath = Join-Path $appRoot "dist"
$workPath = Join-Path $appRoot "build"
$entryPoint = Join-Path $appRoot "main.py"

$env:PYTHONPATH = "$buildTools;$env:PYTHONPATH"

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name NDEX_Launcher `
  --paths $appRoot `
  --paths $repoRoot `
  --collect-submodules ndex_launcher `
  --collect-submodules ndex_common `
  --hidden-import ndex_launcher.state `
  --hidden-import ndex_common.launch `
  --hidden-import ndex_common.settings `
  --hidden-import ndex_common.branding `
  --distpath $distPath `
  --workpath $workPath `
  --specpath $workPath `
  --add-data "$repoRoot\assets\branding;assets\branding" `
  --icon "$repoRoot\assets\branding\ndex_icon.ico" `
  $entryPoint
