"""File-boundary cancellation shared by Image Manager operations."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Callable, Iterator

from ..core.models import ImageRecord

ProgressCallback = Callable[[int, int, Path], None]


def operation_records(
    records: list[ImageRecord],
    summary,
    cancel_event: Event | None,
    progress_callback: ProgressCallback | None,
) -> Iterator[ImageRecord]:
    """Finish the active file, retaining every unprocessed source for reports."""
    for index, record in enumerate(records):
        if cancel_event is not None and cancel_event.is_set():
            summary.cancelled = True
            remaining = records[index:]
            summary.errors += len(remaining)
            summary.items.extend(
                {"path": str(item.file_path), "status": "failed", "detail": "not run: cancelled"}
                for item in remaining
            )
            break
        if progress_callback:
            progress_callback(index, len(records), record.file_path)
        yield record
        if progress_callback:
            progress_callback(index + 1, len(records), record.file_path)
