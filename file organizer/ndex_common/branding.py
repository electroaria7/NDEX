"""Shared NDEX branding — titles, icons, and bundle path helpers.

Canonical location for branding values used by all NDEX apps.
``src.branding`` re-exports this module for backward compatibility.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "NDEX"
LEGACY_APP_NAME = "DSB"
NDEX_ONE_TITLE = "NDEX One"
NDEX_IMAGE_MANAGER_TITLE = "NDEX Image Manager"
NDEX_AUTO_SELECTOR_TITLE = "NDEX Auto Selector"
NDEX_LAUNCHER_TITLE = "NDEX Launcher"

BRANDING_DIR = Path("assets") / "branding"
APP_ICON_ICO = BRANDING_DIR / "ndex_icon.ico"
APP_ICON_32 = BRANDING_DIR / "ndex_icon_32.png"
APP_ICON_64 = BRANDING_DIR / "ndex_icon_64.png"
APP_WORDMARK_HEADER = BRANDING_DIR / "ndex_wordmark_header.png"


def get_bundle_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def get_branding_asset_path(relative_path: Path) -> Path:
    return get_bundle_dir() / relative_path
