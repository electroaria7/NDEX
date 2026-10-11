from __future__ import annotations

from dataclasses import dataclass, field, replace
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

# Shown in the list so pick state is readable without relying on colour.
PICK_GLYPHS = {"Pick": "\u2713", "Maybe": "?", "Reject": "\u2715", "Unrated": ""}


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
    # Exact on-disk size and mtime; a rescan reuses the record when both match.
    size_bytes: int | None = None
    mtime_ns: int | None = None

    @property
    def effective_datetime(self) -> datetime:
        return self.capture_datetime or self.file_modified_datetime

    @property
    def display_name(self) -> str:
        return self.file_path.name

    @property
    def type_label(self) -> str:
        """Short file-type text for lists: RAW, JPG, or the bare extension."""
        if self.media_type == "raw":
            return "RAW"
        if self.media_type == "jpg":
            return "JPG"
        return self.file_ext.lstrip(".").upper() or "-"

    @property
    def short_datetime(self) -> str:
        return f"{self.effective_datetime:%m-%d %H:%M}"

    @property
    def pick_glyph(self) -> str:
        return PICK_GLYPHS.get(self.pick_status, "")


PICK_STRENGTH_ORDER = ("Pick", "Reject", "Maybe")


def merge_pick_status(statuses) -> str:
    """Strongest state of a shot: any Pick wins, then Reject, then Maybe."""
    present = set(statuses)
    for status in PICK_STRENGTH_ORDER:
        if status in present:
            return status
    return "Unrated"


@dataclass(slots=True)
class Shot:
    """One photo moment: every file in a folder that shares a stem (RAW+JPG pair or a single file)."""

    key: str
    records: list[ImageRecord]

    def __post_init__(self) -> None:
        order = {"jpg": 0, "raw": 1}
        self.records.sort(key=lambda r: (order.get(r.media_type, 2), r.file_path.name.casefold()))

    @property
    def primary(self) -> ImageRecord:
        """The file used for preview and as the row identity: the JPG, else the RAW proxy."""
        return self.records[0]

    @property
    def id(self) -> int | None:
        return self.primary.id

    @property
    def stem(self) -> str:
        return self.primary.file_path.stem

    @property
    def has_jpg(self) -> bool:
        return any(r.media_type == "jpg" for r in self.records)

    @property
    def has_raw(self) -> bool:
        return any(r.media_type == "raw" for r in self.records)

    @property
    def composition(self) -> PairStatus:
        if self.has_jpg and self.has_raw:
            return "raw_jpg_pair"
        if self.has_raw:
            return "raw_only"
        if self.has_jpg:
            return "jpg_only"
        return "unknown"

    @property
    def type_label(self) -> str:
        composition = self.composition
        if composition == "raw_jpg_pair":
            return "RAW+JPG"
        if composition == "raw_only":
            return "RAW"
        if composition == "jpg_only":
            return "JPG"
        return self.primary.type_label

    @property
    def jpg_records(self) -> list[ImageRecord]:
        return [r for r in self.records if r.media_type == "jpg"]

    @property
    def raw_records(self) -> list[ImageRecord]:
        return [r for r in self.records if r.media_type == "raw"]

    @property
    def pick_status(self) -> PickStatus:
        return merge_pick_status(r.pick_status for r in self.records)  # type: ignore[return-value]

    @property
    def rating(self) -> int:
        return max(r.rating for r in self.records)

    @property
    def pick_glyph(self) -> str:
        return PICK_GLYPHS.get(self.pick_status, "")

    @property
    def effective_datetime(self) -> datetime:
        return self.primary.effective_datetime

    @property
    def file_names(self) -> list[str]:
        return [r.file_path.name for r in self.records]

    def records_with_state(self) -> list[ImageRecord]:
        """Copies of every file carrying the shot's single pick/rating state."""
        return [replace(r, pick_status=self.pick_status, rating=self.rating) for r in self.records]


def build_shots(records) -> dict[str, Shot]:
    """Group file records into shots, keeping first-seen order."""
    grouped: dict[str, list[ImageRecord]] = {}
    for record in records:
        grouped.setdefault(record.pair_group_id, []).append(record)
    return {key: Shot(key, members) for key, members in grouped.items()}


def apply_shot_state(records) -> list[ImageRecord]:
    """Give every file of a shot the shot's pick/rating (used by XMP export)."""
    records = list(records)
    state = {key: (shot.pick_status, shot.rating) for key, shot in build_shots(records).items()}
    return [replace(r, pick_status=state[r.pair_group_id][0], rating=state[r.pair_group_id][1]) for r in records]


def shot_matches(shot: Shot, file_filter: str = "all", pick_filter: str = "all", min_rating: int = 0) -> bool:
    """Filters judge a shot's composition, not its individual files."""
    if file_filter == "paired":
        ok = shot.composition == "raw_jpg_pair"
    elif file_filter in ("raw", "raw_only"):
        ok = shot.composition == "raw_only"
    elif file_filter in ("jpg", "jpg_only"):
        ok = shot.composition == "jpg_only"
    elif file_filter == "proxy_failed":
        ok = any(r.proxy_status == "failed" for r in shot.records)
    else:
        ok = True
    if not ok:
        return False
    if pick_filter != "all" and shot.pick_status != pick_filter:
        return False
    return shot.rating >= min_rating


def sort_shots(shots, sort_key: str = "capture_datetime", descending: bool = False) -> list[Shot]:
    def key(shot: Shot):
        primary = shot.primary
        column = {
            "file_name": str(primary.file_path).casefold(),
            "media_type": shot.type_label,
            "pair_status": shot.composition,
            "pick_status": shot.pick_status,
            "rating": shot.rating,
            "backup_status": min(r.backup_status for r in shot.records),
        }.get(sort_key, shot.effective_datetime)
        return (column, str(primary.file_path))

    return sorted(shots, key=key, reverse=descending)


def sort_records(records, sort_key: str = "capture_datetime", descending: bool = False) -> list[ImageRecord]:
    """Order individual files the way the list columns do (used by the split view)."""
    def key(record: ImageRecord):
        column = {
            "file_name": str(record.file_path).casefold(),
            "media_type": record.media_type,
            "pair_status": record.pair_status,
            "pick_status": record.pick_status,
            "rating": record.rating,
            "backup_status": record.backup_status,
        }.get(sort_key, record.effective_datetime)
        return (column, str(record.file_path))

    return sorted(records, key=key, reverse=descending)


@dataclass(slots=True)
class MarkChange:
    """One undoable pick/rating edit; entries are (id, old_pick, old_rating, new_pick, new_rating)."""

    label: str
    entries: list[tuple[int, str, int, str, int]]


class UndoStack:
    """Per-session undo/redo history for marks (a bulk edit is a single step)."""

    def __init__(self, limit: int = 100):
        self.limit = limit
        self._undo: list[MarkChange] = []
        self._redo: list[MarkChange] = []

    def push(self, change: MarkChange) -> None:
        self._undo.append(change)
        del self._undo[: max(0, len(self._undo) - self.limit)]
        self._redo.clear()

    def pop_undo(self) -> MarkChange | None:
        if not self._undo:
            return None
        change = self._undo.pop()
        self._redo.append(change)
        return change

    def pop_redo(self) -> MarkChange | None:
        if not self._redo:
            return None
        change = self._redo.pop()
        self._undo.append(change)
        return change

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def __len__(self) -> int:
        return len(self._undo)


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
    items: list[dict[str, str]] = field(default_factory=list)
    cancelled: bool = False


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
    items: list[dict[str, str]] = field(default_factory=list)
    cancelled: bool = False
