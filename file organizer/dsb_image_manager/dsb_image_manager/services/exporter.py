from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..core.models import DuplicatePolicy, ExportOptions, ExportSummary, ImageRecord

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ExportService:
    def export(self, records: list[ImageRecord], options: ExportOptions) -> ExportSummary:
        summary = ExportSummary(total=len(records))
        options.destination_dir.mkdir(parents=True, exist_ok=True)

        for offset, record in enumerate(records):
            try:
                index = options.start_index + offset
                stem = render_export_stem(record, options.rename_pattern, index)
                destination = options.destination_dir / f"{stem}{record.file_path.suffix}"
                final_path, action = resolve_duplicate(destination, options.duplicate_policy)
                if action == "skip":
                    summary.skipped += 1
                    continue
                if action == "overwrite":
                    summary.overwritten += 1
                shutil.copy2(record.file_path, final_path)
                summary.exported += 1
                summary.exported_paths.append(final_path)
            except Exception as exc:  # pragma: no cover - filesystem failures vary
                summary.errors += 1
                summary.messages.append(f"{record.file_path.name}: {exc}")
        return summary


def render_export_stem(record: ImageRecord, pattern: str, index: int) -> str:
    capture = record.effective_datetime
    tokens = {
        "{date}": capture.strftime("%Y%m%d"),
        "{time}": capture.strftime("%H%M%S"),
        "{index}": f"{index:03d}",
        "{index2}": f"{index:02d}",
        "{index3}": f"{index:03d}",
        "{index4}": f"{index:04d}",
        "{name}": record.file_path.stem,
        "{rating}": str(record.rating),
        "{pick}": record.pick_status,
        "{ext}": record.file_path.suffix.lower().lstrip("."),
    }
    rendered = pattern.strip() or "{date}_{index}_{name}"
    for token, value in tokens.items():
        rendered = rendered.replace(token, value)
    rendered = INVALID_FILENAME_CHARS.sub("_", rendered)
    rendered = re.sub(r"\s+", "_", rendered)
    rendered = rendered.strip(" ._")
    return rendered or record.file_path.stem


def resolve_duplicate(destination_path: Path, duplicate_policy: DuplicatePolicy) -> tuple[Path, str]:
    if not destination_path.exists():
        return destination_path, "copy"
    if duplicate_policy == "skip":
        return destination_path, "skip"
    if duplicate_policy == "overwrite":
        return destination_path, "overwrite"

    stem = destination_path.stem
    suffix = destination_path.suffix
    for index in range(1, 10000):
        candidate = destination_path.with_name(f"{stem}_{index:03d}{suffix}")
        if not candidate.exists():
            return candidate, "copy"
    raise RuntimeError(f"Could not resolve duplicate name for {destination_path}")
