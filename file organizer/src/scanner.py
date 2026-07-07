from __future__ import annotations

from pathlib import Path

from .file_types import get_extensions_for_types
from .folder_manager import build_destination_dir, build_preview, get_file_type_folder
from .models import ScanItem, ScanSummary


def collect_supported_files(source_dir: Path, enabled_types: list[str]) -> list[Path]:
    enabled_extensions = get_extensions_for_types(enabled_types)

    files = [
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in enabled_extensions
    ]
    return sorted(files, key=lambda path: str(path).lower())


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

    files = collect_supported_files(source_dir, enabled_types)
    if logger:
        logger.info(f"Source: {source_dir}")
        logger.info(f"Destination: {backup_root}")
        logger.info(f"Found {len(files)} supported files")

    items: list[ScanItem] = []
    counts = {file_type: 0 for file_type in enabled_types}
    if hasattr(metadata_extractor, "get_capture_datetimes"):
        metadata = metadata_extractor.get_capture_datetimes(files, logger=logger)
    else:
        metadata = {
            file_path: metadata_extractor.get_capture_datetime(file_path, logger=logger)
            for file_path in files
        }

    for index, file_path in enumerate(files, start=1):
        capture_datetime, metadata_source, fallback_used = metadata[file_path]
        file_type = get_file_type_folder(file_path)
        if file_type not in counts:
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
        counts[file_type] += 1

        if progress_callback:
            progress_callback("analyze", index, len(files), file_path.name)

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
