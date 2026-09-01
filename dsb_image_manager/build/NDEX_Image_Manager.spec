# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['dsb_image_manager.dsb_image_manager.core.file_types', 'dsb_image_manager.dsb_image_manager.core.models', 'dsb_image_manager.dsb_image_manager.services.backup', 'dsb_image_manager.dsb_image_manager.services.cache', 'dsb_image_manager.dsb_image_manager.services.catalog', 'dsb_image_manager.dsb_image_manager.services.exporter', 'dsb_image_manager.dsb_image_manager.services.metadata', 'dsb_image_manager.dsb_image_manager.services.scanner', 'dsb_image_manager.dsb_image_manager.ui.tk_app']
hiddenimports += collect_submodules('dsb_image_manager.dsb_image_manager')


a = Analysis(
    ['F:/Github/NDEX/dsb_image_manager/main.py'],
    pathex=['F:/Github/NDEX/dsb_image_manager', 'F:/Github/NDEX'],
    binaries=[],
    datas=[('F:/Github/NDEX/vendor/exiftool', 'vendor/exiftool'), ('F:/Github/NDEX/assets/branding', 'assets/branding')],
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
    name='NDEX_Image_Manager',
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
