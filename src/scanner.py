from __future__ import annotations

import os
from pathlib import Path

from .file_types import get_extensions_for_types
from .folder_manager import build_destination_dir, build_preview, get_file_type_folder
from .models import ScanItem, ScanSummary


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def collect_supported_files(
    source_dir: Path,
    enabled_types: list[str],
    exclude_dir: Path | None = None,
) -> list[Path]:
    """Supported files under ``source_dir``, skipping anything under ``exclude_dir``.

    ``exclude_dir`` is the backup destination: when it sits inside the source,
    scanning it would back up the backups themselves on every run.
    """
    enabled_extensions = get_extensions_for_types(enabled_types)
    excluded = Path(os.path.normcase(os.path.abspath(exclude_dir))) if exclude_dir else None

    def excluded_path(path: Path) -> bool:
        return excluded is not None and _is_within(
            Path(os.path.normcase(os.path.abspath(path))), excluded
        )

    if excluded_path(source_dir):
        return []
    files = []
    for directory, dirs, names in os.walk(source_dir):
        root = Path(directory)
        # Prune before descending: an existing backup can dwarf the source.
        dirs[:] = [name for name in dirs if not excluded_path(root / name)]
        for name in names:
            path = root / name
            if path.suffix.lower() in enabled_extensions and path.is_file():
                files.append(path)
    return sorted(files, key=lambda path: str(path).lower())


def same_folder(first: Path | str, second: Path | str) -> bool:
    """True when both paths name the same folder (case and slashes ignored)."""
    def key(value):
        return os.path.normcase(os.path.abspath(str(value)))

    return key(first) == key(second)


def analyze_source(
    source_dir: Path,
    backup_root: Path,
    metadata_extractor,
    enabled_types: list[str],
    progress_callback=None,
    logger=None,
) -> ScanSummary:
    source_dir = Path(source_dir)
    backup_root = Path(backup_root)

    files = collect_supported_files(source_dir, enabled_types, exclude_dir=backup_root)
    if logger:
        logger.info(f"Source: {source_dir}")
        logger.info(f"Destination: {backup_root}")
        logger.info(f"Found {len(files)} supported files")

    items, counts = build_scan_items(
        files,
        backup_root,
        metadata_extractor,
        enabled_types=enabled_types,
        progress_callback=progress_callback,
        logger=logger,
    )

    preview_rows, folder_tree_lines = build_preview(items, backup_root)

    if items:
        sorted_dates = sorted(item.capture_datetime for item in items)
        date_range = (sorted_dates[0], sorted_dates[-1])
    else:
        date_range = (None, None)

    return ScanSummary(
        source_dir=source_dir,
        backup_root=backup_root,
        items=items,
        counts=counts,
        date_range=date_range,
        preview_rows=preview_rows,
        folder_tree_lines=folder_tree_lines,
    )


def build_scan_items(
    files: list[Path],
    backup_root: Path,
    metadata_extractor,
    enabled_types: list[str] | None = None,
    progress_callback=None,
    logger=None,
) -> tuple[list[ScanItem], dict[str, int]]:
    """Work out where each file belongs in the backup tree.

    ``enabled_types`` of None keeps every file the caller passed in. A retry
    uses that: the files came from a finished job, so the type checkboxes
    showing in the window now have no say over them.
    """
    allowed = set(enabled_types) if enabled_types is not None else None
    items: list[ScanItem] = []
    # Zero rows for every allowed type, so the summary can show "JPG: 0".
    counts: dict[str, int] = {file_type: 0 for file_type in allowed or ()}
    if hasattr(metadata_extractor, "get_capture_datetimes"):
        metadata = metadata_extractor.get_capture_datetimes(files, logger=logger)
    else:
        metadata = {
            file_path: metadata_extractor.get_capture_datetime(file_path, logger=logger)
            for file_path in files
        }

    for index, file_path in enumerate(files, start=1):
        if file_path not in metadata:
            # The extractor skipped it (for example, the file vanished mid-scan).
            continue
        capture_datetime, metadata_source, fallback_used = metadata[file_path]
        file_type = get_file_type_folder(file_path)
        if allowed is not None and file_type not in allowed:
            continue

        destination_dir = build_destination_dir(backup_root, capture_datetime, file_type)
        items.append(
            ScanItem(
                source_path=file_path,
                file_type=file_type,
                capture_datetime=capture_datetime,
                metadata_source=metadata_source,
                destination_dir=destination_dir,
                fallback_used=fallback_used,
            )
        )
        counts[file_type] = counts.get(file_type, 0) + 1

        if progress_callback:
            progress_callback("analyze", index, len(files), file_path.name)

    return items, counts
