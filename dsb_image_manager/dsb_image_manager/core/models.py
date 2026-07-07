from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

PickStatus = Literal["Unrated", "Pick", "Maybe", "Reject"]
ProxyStatus = Literal[
    "not_required",
    "pending",
    "embedded_preview",
    "generated",
    "rendered",
    "failed",
]
PairStatus = Literal["raw_jpg_pair", "raw_only", "jpg_only", "unknown"]
DuplicatePolicy = Literal["rename", "skip", "overwrite"]


@dataclass(slots=True)
class ImageMetadata:
    capture_datetime: datetime | None = None
    camera_model: str = ""
    lens_model: str = ""
    focal_length: str = ""
    exposure_time: str = ""
    aperture: str = ""
    iso: str = ""
    exposure_compensation: str = ""
    white_balance: str = ""
    color_space: str = ""
    width: int | None = None
    height: int | None = None
    file_size: str = ""
    gps: str = ""
    has_exif: bool = False


@dataclass(slots=True)
class ImageRecord:
    id: int | None
    file_path: Path
    file_ext: str
    base_name: str
    media_type: str
    pair_group_id: str
    pair_status: PairStatus
    display_source: Path | None
    proxy_path: Path | None
    thumbnail_path: Path | None
    capture_datetime: datetime | None
    file_modified_datetime: datetime
    camera_model: str = ""
    lens_model: str = ""
    focal_length: str = ""
    exposure_time: str = ""
    aperture: str = ""
    iso: str = ""
    exposure_compensation: str = ""
    white_balance: str = ""
    color_space: str = ""
    width: int | None = None
    height: int | None = None
    file_size: str = ""
    gps: str = ""
    has_exif: bool = False
    has_proxy: bool = False
    proxy_status: ProxyStatus = "pending"
    backup_status: str = "not_backed_up"
    pick_status: PickStatus = "Unrated"
    rating: int = 0
    color_label: str = ""
    selected: bool = False
    note: str = ""

    @property
    def effective_datetime(self) -> datetime:
        return self.capture_datetime or self.file_modified_datetime

    @property
    def display_name(self) -> str:
        return self.file_path.name


@dataclass(slots=True)
class ScanResult:
    source_dir: Path
    catalog_path: Path
    records: list[ImageRecord] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def jpg_count(self) -> int:
        return sum(1 for record in self.records if record.media_type == "jpg")

    @property
    def raw_count(self) -> int:
        return sum(1 for record in self.records if record.media_type == "raw")

    @property
    def pair_count(self) -> int:
        return len({record.pair_group_id for record in self.records if record.pair_status == "raw_jpg_pair"})


@dataclass(slots=True)
class BackupSummary:
    total: int = 0
    copied: int = 0
    skipped: int = 0
    overwritten: int = 0
    errors: int = 0
    messages: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExportOptions:
    destination_dir: Path
    rename_pattern: str = "{date}_{index}_{name}"
    start_index: int = 1
    duplicate_policy: DuplicatePolicy = "rename"


@dataclass(slots=True)
class ExportSummary:
    total: int = 0
    exported: int = 0
    skipped: int = 0
    overwritten: int = 0
    errors: int = 0
    exported_paths: list[Path] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
