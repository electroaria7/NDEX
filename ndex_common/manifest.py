"""Result manifests for backup, extract, export, and Select handoff.

Manifests are JSON files under ``%LOCALAPPDATA%/NDEX/manifests/``. They never
modify photographs; they record what a job copied, skipped, left ambiguous,
or failed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from ndex_common.jsonio import write_json_atomic
from ndex_common.settings import data_dir

KIND = "ndex.manifest"
SCHEMA_VERSION = 1
TYPES = ("backup", "extract", "export", "select_handoff")
FRAME_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff"})


def manifests_dir(root: Path | None = None) -> Path:
    path = (root or data_dir()) / "manifests"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_manifest(
    *,
    type: str,
    app: str,
    source: str = "",
    destination: str = "",
    counts: Mapping[str, int] | None = None,
    items: Iterable[Mapping[str, Any]] | None = None,
    context: Mapping[str, Any] | None = None,
    root: Path | None = None,
) -> Path:
    if type not in TYPES:
        raise ValueError(f"Unknown manifest type: {type}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = manifests_dir(root) / f"{type}-{stamp}.json"
    payload = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "type": type,
        "app": app,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "destination": destination,
        "counts": dict(counts or {}),
        "items": [dict(item) for item in (items or ())],
        "context": dict(context or {}),
    }
    write_json_atomic(path, payload)
    latest = manifests_dir(root) / f"latest-{app}-{type}.json"
    write_json_atomic(latest, payload)
    return path


def load_manifest(path: Path) -> dict[str, Any] | None:
    try:
        import json

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") not in (KIND, None, ""):
        return None
    if payload.get("type") not in TYPES:
        return None
    return payload


def frame_ready_paths(paths: Iterable[Path]) -> list[Path]:
    """Keep files Frame can import (JPG/PNG/TIFF). Missing paths are dropped."""
    ready: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        candidate = Path(path)
        if candidate.suffix.casefold() not in FRAME_SUFFIXES or not candidate.is_file():
            continue
        key = str(candidate.resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)
        ready.append(candidate)
    return ready


def handoff_files(manifest: Mapping[str, Any]) -> list[Path]:
    files: list[Path] = []
    for raw in manifest.get("files") or ():
        files.append(Path(str(raw)))
    for item in manifest.get("items") or ():
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if path:
            files.append(Path(str(path)))
    return frame_ready_paths(files)
