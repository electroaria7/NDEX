"""Backward-compatibility shim — canonical branding lives in ndex_common.branding.

All NDEX apps historically import from ``src.branding``; keep this module
as a re-export so existing imports and PyInstaller builds keep working.
"""

from __future__ import annotations

from ndex_common.branding import (  # noqa: F401
    APP_ICON_32,
    APP_ICON_64,
    APP_ICON_ICO,
    APP_NAME,
    APP_WORDMARK_HEADER,
    BRANDING_DIR,
    LEGACY_APP_NAME,
    NDEX_AUTO_SELECTOR_TITLE,
    NDEX_IMAGE_MANAGER_TITLE,
    NDEX_LAUNCHER_TITLE,
    NDEX_ONE_TITLE,
    get_branding_asset_path,
    get_bundle_dir,
)
