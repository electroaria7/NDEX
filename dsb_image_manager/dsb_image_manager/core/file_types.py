from __future__ import annotations

from pathlib import Path

from ndex_common.raw_formats import RAW_EXTENSIONS as _SHARED_RAW_EXTENSIONS

JPG_EXTENSIONS = {".jpg", ".jpeg"}
RAW_EXTENSIONS = set(_SHARED_RAW_EXTENSIONS)
SUPPORTED_EXTENSIONS = JPG_EXTENSIONS | RAW_EXTENSIONS


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def media_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in JPG_EXTENSIONS:
        return "jpg"
    if suffix in RAW_EXTENSIONS:
        return "raw"
    return "unknown"


def backup_type_folder(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"jpg", "jpeg"}:
        return "JPG"
    return suffix.upper() or "UNKNOWN"
