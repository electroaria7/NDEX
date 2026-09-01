"""Shared NDEX settings file (Adobe CC-style settings sync).

All NDEX apps read and write one file: ``%LOCALAPPDATA%/NDEX/config/settings.json``.

Layout:
- Top-level flat keys belong to NDEX One (legacy layout, kept for
  backward compatibility with existing user settings).
- Other apps use namespaced sections: ``"image_manager": {...}``,
  ``"auto_selector": {...}``, and ``"shared": {...}`` for cross-app values.

Writers must merge into the existing file so one app never destroys
another app's settings.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

APP_NAME = "NDEX"
SECTION_KEYS = ("shared", "image_manager", "auto_selector", "frame")


def settings_path() -> Path:
    return _config_dir() / "settings.json"


def load_all() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def get_section(section: str, defaults: dict | None = None) -> dict:
    """Return one app's section merged over the given defaults."""
    merged = deepcopy(defaults) if defaults else {}
    stored = load_all().get(section)
    if isinstance(stored, dict):
        merged.update(stored)
    return merged


def update_section(section: str, values: dict) -> None:
    """Merge values into one section, preserving everything else in the file."""
    data = load_all()
    current = data.get(section)
    if not isinstance(current, dict):
        current = {}
    current.update(values)
    data[section] = current
    save_all(data)


def save_all(data: dict) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=True, indent=2)


def _config_dir() -> Path:
    candidates: list[Path] = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / APP_NAME / "config")
    candidates.append(Path.home() / "AppData" / "Local" / APP_NAME / "config")
    candidates.append(Path.home() / f".{APP_NAME.lower()}" / "config")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    return candidates[-1]
