"""Export pick/rating state to XMP sidecars (shared NDEX data contract)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from threading import Event
from typing import Iterable

from ndex_common.xmp import sidecar_path_for, write_xmp_sidecar

from ..core.models import ImageRecord
from .operations import ProgressCallback, operation_records

SELECTED_LABEL = "NDEX Selected"
PICK_KEYWORDS = {
    "Pick": "NDEX Pick",
    "Maybe": "NDEX Maybe",
    "Reject": "NDEX Reject",
}


@dataclass(slots=True)
class XmpExportSummary:
    total: int = 0
    written: int = 0
    skipped: int = 0
    errors: int = 0
    messages: list[str] = field(default_factory=list)
    items: list[dict[str, str]] = field(default_factory=list)
    cancelled: bool = False


class XmpExportService:
    """Writes .xmp sidecars next to original files. Originals are never modified."""

    def export(
        self,
        records: Iterable[ImageRecord],
        include_unrated: bool = False,
        *,
        cancel_event: Event | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> XmpExportSummary:
        records = list(records)
        summary = XmpExportSummary(total=len(records))

        for record in operation_records(records, summary, cancel_event, progress_callback):
            has_state = record.pick_status != "Unrated" or record.rating > 0
            if not has_state and not include_unrated:
                # Nothing to write, but an earlier export may have left NDEX
                # pick state behind; take it out of an existing sidecar only.
                if self._has_ndex_state(record):
                    try:
                        write_xmp_sidecar(
                            record.file_path,
                            remove_keywords=PICK_KEYWORDS.values(),
                            clear_label_if=(SELECTED_LABEL,),
                        )
                        summary.written += 1
                        summary.items.append({"path": str(record.file_path), "destination": str(sidecar_path_for(record.file_path)), "status": "written"})
                    except (OSError, ValueError, TypeError, ET.ParseError) as exc:
                        summary.errors += 1
                        summary.messages.append(f"{record.file_path.name}: {exc}")
                        summary.items.append({"path": str(record.file_path), "status": "failed", "detail": str(exc)})
                else:
                    summary.skipped += 1
                    summary.items.append({"path": str(record.file_path), "status": "skipped"})
                continue
            try:
                keywords = []
                pick_keyword = PICK_KEYWORDS.get(record.pick_status)
                if pick_keyword:
                    keywords.append(pick_keyword)
                label = SELECTED_LABEL if record.pick_status == "Pick" else None
                write_xmp_sidecar(
                    record.file_path,
                    rating=record.rating,
                    label=label,
                    keywords=keywords,
                    remove_keywords=PICK_KEYWORDS.values(),
                    clear_label_if=(SELECTED_LABEL,),
                )
                summary.written += 1
                summary.items.append({"path": str(record.file_path), "destination": str(sidecar_path_for(record.file_path)), "status": "written"})
            except (OSError, ValueError, TypeError, ET.ParseError) as exc:
                summary.errors += 1
                summary.messages.append(f"{record.file_path.name}: {exc}")
                summary.items.append({"path": str(record.file_path), "status": "failed", "detail": str(exc)})

        return summary

    @staticmethod
    def _has_ndex_state(record: ImageRecord) -> bool:
        xmp_path = sidecar_path_for(record.file_path)
        try:
            text = xmp_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return SELECTED_LABEL in text or any(keyword in text for keyword in PICK_KEYWORDS.values())
