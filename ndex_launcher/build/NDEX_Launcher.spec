# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['ndex_launcher.state', 'ndex_common.launch', 'ndex_common.settings', 'ndex_common.branding']
hiddenimports += collect_submodules('ndex_launcher')
hiddenimports += collect_submodules('ndex_common')


a = Analysis(
    ['F:/Github/NDEX/ndex_launcher/main.py'],
    pathex=['F:/Github/NDEX/ndex_launcher', 'F:/Github/NDEX'],
    binaries=[],
    datas=[('F:/Github/NDEX/assets/branding', 'assets/branding')],
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name='NDEX_Launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['F:/Github/NDEX/assets/branding/ndex_icon.ico'],
)
