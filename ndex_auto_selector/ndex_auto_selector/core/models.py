from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

DuplicatePolicy = Literal["rename", "skip", "overwrite"]


@dataclass(slots=True)
class SelectionMatch:
    jpg_path: Path
    raw_path: Path | None
    status: str

    @property
    def file_stem(self) -> str:
        return self.jpg_path.stem


@dataclass(slots=True)
class AnalysisSummary:
    raw_source_dir: Path
    selected_jpg_dir: Path
    matches: list[SelectionMatch]

    @property
    def selected_count(self) -> int:
        return len(self.matches)

    @property
    def matched_count(self) -> int:
        return sum(1 for match in self.matches if match.status == "matched")

    @property
    def missing_count(self) -> int:
        return sum(1 for match in self.matches if match.status == "missing")

    @property
    def ambiguous_count(self) -> int:
        return sum(1 for match in self.matches if match.status == "ambiguous")


@dataclass(slots=True)
class CopyResult:
    total: int
    copied: int = 0
    xmp_written: int = 0
    skipped: int = 0
    overwritten: int = 0
    missing: int = 0
    ambiguous: int = 0
    errors: int = 0
    messages: list[str] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
