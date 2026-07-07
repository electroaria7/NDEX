from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .file_types import FILE_TYPE_ORDER, get_file_type_for_path
from .models import PreviewRow, ScanItem


def get_file_type_folder(file_path: Path) -> str:
    return get_file_type_for_path(file_path)


def build_relative_destination_dir(capture_datetime: datetime, file_type_folder: str) -> Path:
    return Path(
        capture_datetime.strftime("%Y"),
        capture_datetime.strftime("%m"),
        capture_datetime.strftime("%m%d"),
        file_type_folder,
    )


def build_destination_dir(
    backup_root: Path,
    capture_datetime: datetime,
    file_type_folder: str,
) -> Path:
    return backup_root / build_relative_destination_dir(capture_datetime, file_type_folder)


def resolve_duplicate_path(destination_path: Path) -> Path:
    if not destination_path.exists():
        return destination_path

    stem = destination_path.stem
    suffix = destination_path.suffix
    counter = 1
    while True:
        candidate = destination_path.parent / f"{stem}_{counter:03d}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def build_preview(items: list[ScanItem], backup_root: Path) -> tuple[list[PreviewRow], list[str]]:
    grouped: dict[Path, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    folder_status: dict[Path, list[bool]] = defaultdict(list)

    for item in items:
        rel_date_path = item.destination_dir.relative_to(backup_root).parent
        grouped[rel_date_path][item.file_type] += 1
        folder_status[rel_date_path].append(item.destination_dir.exists())

    rows: list[PreviewRow] = []
    lines = [backup_root.as_posix() + "/"]

    for rel_date_path in sorted(grouped):
        statuses = folder_status[rel_date_path]
        if all(statuses):
            status = "Existing"
        elif any(statuses):
            status = "Mixed"
        else:
            status = "New"

        counts = grouped[rel_date_path]
        rows.append(
            PreviewRow(
                date_label=f"{rel_date_path.parts[0]}-{rel_date_path.parts[1]}-{rel_date_path.parts[2][2:4]}",
                folder_rel_path=rel_date_path,
                type_counts=dict(counts),
                status=status,
            )
        )
        ordered_types = [file_type for file_type in FILE_TYPE_ORDER if counts.get(file_type, 0) > 0]
        extra_types = sorted(file_type for file_type in counts if file_type not in FILE_TYPE_ORDER)
        for file_type in [*ordered_types, *extra_types]:
            count = counts.get(file_type, 0)
            if count == 0:
                continue
            target_dir = backup_root / rel_date_path / file_type
            line_status = "existing" if target_dir.exists() else "new"
            lines.append(f"  {rel_date_path.as_posix()}/{file_type}  [{line_status}] ({count})")

    return rows, lines
