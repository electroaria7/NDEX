"""Shared NDEX settings file (Adobe CC-style settings sync).

All NDEX apps read and write one file: ``%LOCALAPPDATA%/NDEX/config/settings.json``.

Layout:
- Top-level flat keys belong to NDEX One (legacy layout, kept for
  backward compatibility with existing user settings).
- Other apps use namespaced sections: ``"image_manager": {...}``,
  ``"auto_selector": {...}``, ``"frame": {...}``, ``"launcher": {...}``,
  ``"ndex_one": {...}``, and ``"shared": {...}`` for cross-app values.
- ``schema_version`` records which layout migrations have been applied.

Writers take a process lock, reload the latest file, merge, then replace
the file atomically so one app never destroys another app's settings.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Callable, Iterator

from ndex_common.jsonio import write_json_atomic
from ndex_common.locking import file_lock

APP_NAME = "NDEX"
SCHEMA_VERSION = 1
SECTION_KEYS = ("shared", "image_manager", "auto_selector", "frame", "launcher", "ndex_one")


def data_dir() -> Path:
    """``%LOCALAPPDATA%/NDEX`` (parent of the config folder)."""
    return _config_dir().parent


def settings_path() -> Path:
    return _config_dir() / "settings.json"


def load_all(*, strict_io: bool = False) -> dict:
    return migrate(_read_unlocked(settings_path(), strict_io=strict_io))


def get_section(section: str, defaults: dict | None = None) -> dict:
    """Return one app's section merged over the given defaults."""
    merged = deepcopy(defaults) if defaults else {}
    stored = load_all().get(section)
    if isinstance(stored, dict):
        merged.update(stored)
    return merged


def update_section(section: str, values: dict) -> None:
    """Merge values into one section, preserving everything else in the file."""

    def mutator(data: dict) -> dict:
        current = data.get(section)
        if not isinstance(current, dict):
            current = {}
        else:
            current = dict(current)
        current.update(values)
        data[section] = current
        return data

    atomic_update(mutator)


def save_all(data: dict) -> None:
    """Replace the settings file. Prefer ``update_section`` or ``atomic_update``."""
    atomic_update(lambda _existing: dict(data))


def atomic_update(mutator: Callable[[dict], dict], path: Path | None = None) -> dict:
    """Reload, migrate, apply ``mutator``, and atomically write under a file lock."""
    target = path or settings_path()
    with settings_lock(target):
        _quarantine_unparseable(target)
        current = migrate(_read_unlocked(target))
        updated = mutator(deepcopy(current))
        if not isinstance(updated, dict):
            raise TypeError("settings mutator must return a dict")
        _write_unlocked(target, updated)
        return updated


def migrate(data: dict | None) -> dict:
    """Return settings upgraded to the current schema without writing."""
    result = dict(data) if isinstance(data, dict) else {}
    version = _schema_version(result)
    if version < 1:
        for key in SECTION_KEYS:
            if key in result and not isinstance(result[key], dict):
                result[key] = {}
        result["schema_version"] = SCHEMA_VERSION
        version = SCHEMA_VERSION
    if version < SCHEMA_VERSION:
        result["schema_version"] = SCHEMA_VERSION
    for key in SECTION_KEYS:
        if key in result and not isinstance(result[key], dict):
            result[key] = {}
    result["schema_version"] = SCHEMA_VERSION
    return result


@contextmanager
def settings_lock(path: Path | None = None) -> Iterator[None]:
    """Exclusive lock for one settings file (Windows ``msvcrt`` / POSIX ``fcntl``)."""
    target = path or settings_path()
    with file_lock(target.with_name(f"{target.name}.lock")):
        yield


def _schema_version(data: dict) -> int:
    raw = data.get("schema_version", 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _read_unlocked(path: Path, *, strict_io: bool = False) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (ValueError, FileNotFoundError):
        # ValueError covers JSONDecodeError and UnicodeDecodeError.
        return {}
    except OSError:
        if strict_io:
            raise
        return {}
    return data if isinstance(data, dict) else {}


def _is_parseable(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return isinstance(json.load(handle), dict)
    except (ValueError, OSError):
        return False


def _quarantine_unparseable(path: Path) -> None:
    """Move an unreadable settings file aside so a write cannot destroy it.

    If a parseable ``.bak`` exists, the settings file is restored from it so
    the other apps' sections survive.
    """
    if not path.exists() or _is_parseable(path):
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    corrupt = path.with_name(f"{path.name}.corrupt-{stamp}")
    counter = 1
    while corrupt.exists():
        corrupt = path.with_name(f"{path.name}.corrupt-{stamp}-{counter}")
        counter += 1
    try:
        os.replace(path, corrupt)
    except OSError:
        return
    backup = path.with_name(f"{path.name}.bak")
    if backup.exists() and _is_parseable(backup):
        try:
            shutil.copy2(backup, path)
        except OSError:
            pass


def _write_unlocked(path: Path, data: dict) -> None:
    payload = migrate(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f"{path.name}.bak")
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
    write_json_atomic(path, payload)


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
