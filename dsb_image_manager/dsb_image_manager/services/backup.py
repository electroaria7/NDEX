from __future__ import annotations

import shutil
from pathlib import Path

from ..core.file_types import backup_type_folder
from ..core.models import BackupSummary, DuplicatePolicy, ImageRecord


class BackupService:
    def backup(
        self,
        records: list[ImageRecord],
        destination_root: Path,
        duplicate_policy: DuplicatePolicy = "rename",
    ) -> BackupSummary:
        summary = BackupSummary(total=len(records))
        destination_root = Path(destination_root)

        for record in sorted(records, key=lambda item: (item.effective_datetime, item.file_path.name.lower())):
            try:
                destination_dir = self.destination_dir(destination_root, record)
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination_path = destination_dir / record.file_path.name
                final_path, action = self._resolve_duplicate(destination_path, duplicate_policy)
                if action == "skip":
                    summary.skipped += 1
                    continue
                if action == "overwrite":
                    summary.overwritten += 1
                shutil.copy2(record.file_path, final_path)
                summary.copied += 1
            except Exception as exc:  # pragma: no cover - filesystem errors vary
                summary.errors += 1
                summary.messages.append(f"{record.file_path.name}: {exc}")
        return summary

    @staticmethod
    def destination_dir(destination_root: Path, record: ImageRecord) -> Path:
        capture = record.effective_datetime
        return (
            destination_root
            / f"{capture.year:04d}"
            / f"{capture.month:02d}"
            / f"{capture.month:02d}{capture.day:02d}"
            / backup_type_folder(record.file_path)
        )

    @staticmethod
    def _resolve_duplicate(destination_path: Path, duplicate_policy: DuplicatePolicy) -> tuple[Path, str]:
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
