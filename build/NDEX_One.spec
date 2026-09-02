# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).parent
datas = [
    (str(project_root / "config" / "settings.json"), "config"),
    (str(project_root / "assets" / "branding"), "assets/branding"),
]

exiftool_dir = project_root / "vendor" / "exiftool"
exiftool_exe = exiftool_dir / "exiftool.exe"
exiftool_files_dir = exiftool_dir / "exiftool_files"
if exiftool_exe.exists():
    datas.append((str(exiftool_exe), "vendor/exiftool"))
if exiftool_files_dir.exists():
    for path in exiftool_files_dir.rglob("*"):
        if path.is_file():
            relative_parent = path.parent.relative_to(exiftool_dir)
            target_dir = Path("vendor", "exiftool", relative_parent).as_posix()
            datas.append((str(path), target_dir))


a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("ndex_common"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NDEX_One",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(project_root / "assets" / "branding" / "ndex_icon.ico"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NDEX_One",
)
