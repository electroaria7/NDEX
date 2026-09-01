"""Source discovery and inexpensive image header analysis."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from ndex_frame.core.models import SourceItem

SUPPORTED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff"})
_ORIENTATION_TAG = 274
_ROTATED_ORIENTATIONS = frozenset({5, 6, 7, 8})
_MISSING_ICC_WARNING = "색상 프로필 없음"


def _normalised_path_key(path: Path) -> str:
    return os.path.normcase(str(path))


def _is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES


def discover_files(paths: list[Path], recursive: bool = False) -> list[Path]:
    """Return supported selected files once, in stable case-insensitive order."""
    discovered: dict[str, Path] = {}
    for selected_path in paths:
        resolved = selected_path.resolve()
        candidates = resolved.rglob("*") if recursive and resolved.is_dir() else (
            resolved.iterdir() if resolved.is_dir() else (resolved,)
        )
        for candidate in candidates:
            if not _is_supported_image(candidate):
                continue
            source = candidate.resolve()
            discovered.setdefault(_normalised_path_key(source), source)

    return sorted(discovered.values(), key=lambda path: _normalised_path_key(path))


def analyze_source(path: Path) -> SourceItem:
    """Read source dimensions and metadata without loading the pixel buffer."""
    source = path.resolve()
    with Image.open(source) as image:
        width, height = image.size
        orientation = image.getexif().get(_ORIENTATION_TAG, 1)
        if orientation in _ROTATED_ORIENTATIONS:
            width, height = height, width
        has_icc = bool(image.info.get("icc_profile"))

    warnings = () if has_icc else (_MISSING_ICC_WARNING,)
    return SourceItem(
        path=source,
        oriented_width=width,
        oriented_height=height,
        has_icc=has_icc,
        warnings=warnings,
    )
