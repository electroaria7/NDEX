"""Export pick/rating state to XMP sidecars (shared NDEX data contract)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterable

from ndex_common.xmp import sidecar_path_for, write_xmp_sidecar

from ..core.models import ImageRecord

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


class XmpExportService:
    """Writes .xmp sidecars next to original files. Originals are never modified."""

    def export(
        self,
        records: Iterable[ImageRecord],
        include_unrated: bool = False,
    ) -> XmpExportSummary:
        records = list(records)
        summary = XmpExportSummary(total=len(records))

        for record in records:
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
                    except (OSError, ValueError, TypeError, ET.ParseError) as exc:
                        summary.errors += 1
                        summary.messages.append(f"{record.file_path.name}: {exc}")
                else:
                    summary.skipped += 1
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
            except (OSError, ValueError, TypeError, ET.ParseError) as exc:
                summary.errors += 1
                summary.messages.append(f"{record.file_path.name}: {exc}")

        return summary

    @staticmethod
    def _has_ndex_state(record: ImageRecord) -> bool:
        xmp_path = sidecar_path_for(record.file_path)
        try:
            text = xmp_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return SELECTED_LABEL in text or any(keyword in text for keyword in PICK_KEYWORDS.values())
