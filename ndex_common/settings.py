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
import sys
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Callable, Iterator

from ndex_common.jsonio import write_json_atomic

APP_NAME = "NDEX"
SCHEMA_VERSION = 1
SECTION_KEYS = ("shared", "image_manager", "auto_selector", "frame", "launcher", "ndex_one")
_THREAD_LOCK = threading.Lock()


def settings_path() -> Path:
    return _config_dir() / "settings.json"


def load_all() -> dict:
    return migrate(_read_unlocked(settings_path()))


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
    lock_path = target.with_name(f"{target.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _THREAD_LOCK:
        handle = lock_path.open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                if handle.read(1) == b"":
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _schema_version(data: dict) -> int:
    raw = data.get("schema_version", 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _read_unlocked(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


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
