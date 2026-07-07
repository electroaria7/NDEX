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
  --name NDEX_Auto_Selector `
  --paths $appRoot `
  --paths $repoRoot `
  --collect-submodules ndex_auto_selector.ndex_auto_selector `
  --hidden-import ndex_auto_selector.ndex_auto_selector.core.models `
  --hidden-import ndex_auto_selector.ndex_auto_selector.services.selector `
  --hidden-import ndex_auto_selector.ndex_auto_selector.ui.tk_app `
  --distpath $distPath `
  --workpath $workPath `
  --specpath $workPath `
  --add-data "$repoRoot\assets\branding;assets\branding" `
  --icon "$repoRoot\assets\branding\ndex_icon.ico" `
  $entryPoint
