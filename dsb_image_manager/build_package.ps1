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
  --name NDEX_Image_Manager `
  --paths $appRoot `
  --paths $repoRoot `
  --collect-submodules dsb_image_manager.dsb_image_manager `
  --hidden-import dsb_image_manager.dsb_image_manager.core.file_types `
  --hidden-import dsb_image_manager.dsb_image_manager.core.models `
  --hidden-import dsb_image_manager.dsb_image_manager.services.backup `
  --hidden-import dsb_image_manager.dsb_image_manager.services.cache `
  --hidden-import dsb_image_manager.dsb_image_manager.services.catalog `
  --hidden-import dsb_image_manager.dsb_image_manager.services.exporter `
  --hidden-import dsb_image_manager.dsb_image_manager.services.metadata `
  --hidden-import dsb_image_manager.dsb_image_manager.services.scanner `
  --hidden-import dsb_image_manager.dsb_image_manager.ui.tk_app `
  --distpath $distPath `
  --workpath $workPath `
  --specpath $workPath `
  --add-data "$repoRoot\vendor\exiftool;vendor\exiftool" `
  --add-data "$repoRoot\assets\branding;assets\branding" `
  --icon "$repoRoot\assets\branding\ndex_icon.ico" `
  $entryPoint
