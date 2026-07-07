from __future__ import annotations

import os
from shutil import copy2
import sys
from pathlib import Path

from .branding import APP_NAME, LEGACY_APP_NAME

LOCAL_DATA_DIR = ".ndex_data"
LEGACY_LOCAL_DATA_DIR = ".dsb_data"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_bundle_dir() -> Path:
    from .branding import get_bundle_dir as get_branding_bundle_dir

    return get_branding_bundle_dir()


def get_executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_user_data_dir() -> Path:
    candidates: list[Path] = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / APP_NAME)

    candidates.append(Path.home() / "AppData" / "Local" / APP_NAME)
    candidates.append(get_executable_dir() / LOCAL_DATA_DIR)
    candidates.append(Path.cwd() / LOCAL_DATA_DIR)
    candidates.extend(_legacy_user_data_candidates())

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            _migrate_legacy_config(candidate)
            probe = candidate / ".write_test"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except OSError:
            continue

    raise PermissionError(f"{APP_NAME} could not create a writable user data directory.")


def get_user_config_dir() -> Path:
    config_dir = get_user_data_dir() / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_user_log_dir() -> Path:
    log_dir = get_user_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_default_settings_template_path() -> Path:
    return get_bundle_dir() / "config" / "settings.json"


def find_bundled_exiftool() -> Path | None:
    candidates = [
        get_executable_dir() / "vendor" / "exiftool" / "exiftool.exe",
        get_executable_dir() / "exiftool.exe",
        get_bundle_dir() / "vendor" / "exiftool" / "exiftool.exe",
        get_bundle_dir() / "exiftool.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _legacy_user_data_candidates() -> list[Path]:
    candidates: list[Path] = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / LEGACY_APP_NAME)
    candidates.append(Path.home() / "AppData" / "Local" / LEGACY_APP_NAME)
    candidates.append(get_executable_dir() / LEGACY_LOCAL_DATA_DIR)
    candidates.append(Path.cwd() / LEGACY_LOCAL_DATA_DIR)
    return candidates


def _migrate_legacy_config(target_dir: Path) -> None:
    target_config = target_dir / "config" / "settings.json"
    if target_config.exists():
        return

    for legacy_dir in _legacy_user_data_candidates():
        legacy_config = legacy_dir / "config" / "settings.json"
        if legacy_config.exists() and legacy_config != target_config:
            target_config.parent.mkdir(parents=True, exist_ok=True)
            copy2(legacy_config, target_config)
            return
