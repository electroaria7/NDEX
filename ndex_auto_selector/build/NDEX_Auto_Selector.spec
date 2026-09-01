# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['ndex_auto_selector.ndex_auto_selector.core.models', 'ndex_auto_selector.ndex_auto_selector.services.selector', 'ndex_auto_selector.ndex_auto_selector.ui.tk_app']
hiddenimports += collect_submodules('ndex_auto_selector.ndex_auto_selector')


a = Analysis(
    ['F:/Github/NDEX/ndex_auto_selector/main.py'],
    pathex=['F:/Github/NDEX/ndex_auto_selector', 'F:/Github/NDEX'],
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
    name='NDEX_Auto_Selector',
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
