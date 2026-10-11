"""Source discovery and inexpensive image header analysis."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from ndex_frame.core.messages import NO_PROFILE_WARNING
from ndex_frame.core.models import SourceItem

SUPPORTED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff"})
_ORIENTATION_TAG = 274
_ROTATED_ORIENTATIONS = frozenset({5, 6, 7, 8})
RAW_SUFFIXES = frozenset({
    ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".dng", ".raf", ".orf",
    ".rw2", ".pef", ".srw", ".x3f", ".3fr", ".erf", ".kdc", ".mrw", ".raw", ".rwl", ".iiq",
})
_MISSING_ICC_WARNING = NO_PROFILE_WARNING


def _normalised_path_key(path: Path) -> str:
    return os.path.normcase(str(path))


def _is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES


@dataclass(slots=True)
class ScanResult:
    """Supported files plus what was left out, so an import can say so."""

    files: list[Path]
    raw_skipped: list[Path] = field(default_factory=list)
    unsupported: list[Path] = field(default_factory=list)


def scan_paths(paths: list[Path], recursive: bool = False) -> ScanResult:
    """Supported files once, in stable case-insensitive order, and the RAW/other skips.

    Unsupported files are only reported when selected directly: a folder
    full of sidecars should not read as a pile of problems.
    """
    discovered: dict[str, Path] = {}
    raw: dict[str, Path] = {}
    other: dict[str, Path] = {}
    for selected_path in paths:
        resolved = selected_path.resolve()
        is_folder = resolved.is_dir()
        candidates = resolved.rglob("*") if recursive and is_folder else (
            resolved.iterdir() if is_folder else (resolved,)
        )
        for candidate in candidates:
            if _is_supported_image(candidate):
                source = candidate.resolve()
                discovered.setdefault(_normalised_path_key(source), source)
            elif candidate.suffix.casefold() in RAW_SUFFIXES and candidate.is_file():
                raw.setdefault(_normalised_path_key(candidate), candidate)
            elif not is_folder and candidate.is_file():
                other.setdefault(_normalised_path_key(candidate), candidate)

    return ScanResult(
        sorted(discovered.values(), key=lambda path: _normalised_path_key(path)),
        sorted(raw.values(), key=lambda path: _normalised_path_key(path)),
        sorted(other.values(), key=lambda path: _normalised_path_key(path)),
    )


def discover_files(paths: list[Path], recursive: bool = False) -> list[Path]:
    """Return supported selected files once, in stable case-insensitive order."""
    return scan_paths(paths, recursive).files


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
