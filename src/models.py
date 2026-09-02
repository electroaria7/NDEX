from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

FileType = str
DuplicatePolicy = Literal["rename", "skip", "overwrite", "smart"]
VerifyMode = Literal["none", "size", "sha256"]


@dataclass(slots=True)
class ScanItem:
    source_path: Path
    file_type: FileType
    capture_datetime: datetime
    metadata_source: str
    destination_dir: Path
    fallback_used: bool = False


@dataclass(slots=True)
class PreviewRow:
    date_label: str
    folder_rel_path: Path
    type_counts: dict[str, int]
    status: str


@dataclass(slots=True)
class ScanSummary:
    source_dir: Path
    backup_root: Path
    items: list[ScanItem]
    counts: dict[str, int]
    date_range: tuple[datetime | None, datetime | None]
    preview_rows: list[PreviewRow]
    folder_tree_lines: list[str]


@dataclass(slots=True)
class BackupResult:
    total: int
    copied: int = 0
    verified: int = 0
    verification_failed: int = 0
    skipped: int = 0
    overwritten: int = 0
    errors: int = 0
    cancelled: bool = False
    dry_run: bool = False
    messages: list[str] = field(default_factory=list)
    # One entry per file the backup actually reached, for the job manifest.
    items: list[dict] = field(default_factory=list)
