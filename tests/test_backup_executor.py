from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.backup_executor import TEMP_SUFFIX, execute_backup
from src.models import ScanItem


def _make_item(source_file: Path, destination_dir: Path, file_type: str = "cr3") -> ScanItem:
    return ScanItem(
        source_path=source_file,
        file_type=file_type,
        capture_datetime=datetime(2026, 5, 3, 12, 0, 0),
        metadata_source="modified_time",
        destination_dir=destination_dir,
    )


class BackupExecutorTests(unittest.TestCase):
    def test_duplicate_rename_creates_numbered_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "source.CR3"
            source_file.write_text("camera-file", encoding="utf-8")

            destination_dir = root / "backup" / "2026" / "05" / "0503" / "cr3"
            destination_dir.mkdir(parents=True)
            (destination_dir / "source.CR3").write_text("existing", encoding="utf-8")

            item = ScanItem(
                source_path=source_file,
                file_type="cr3",
                capture_datetime=datetime(2026, 5, 3, 12, 0, 0),
                metadata_source="modified_time",
                destination_dir=destination_dir,
            )

            result = execute_backup([item], duplicate_policy="rename", dry_run=False)

            self.assertEqual(result.copied, 1)
            self.assertEqual(result.verified, 1)
            self.assertTrue((destination_dir / "source_001.CR3").exists())

    def test_sha256_verification_succeeds_after_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "source.JPG"
            source_file.write_bytes(b"camera-file")

            destination_dir = root / "backup" / "2026" / "05" / "0503" / "jpg"
            item = ScanItem(
                source_path=source_file,
                file_type="jpg",
                capture_datetime=datetime(2026, 5, 3, 12, 0, 0),
                metadata_source="modified_time",
                destination_dir=destination_dir,
            )

            result = execute_backup([item], duplicate_policy="rename", dry_run=False, verify_mode="sha256")

            self.assertEqual(result.copied, 1)
            self.assertEqual(result.verified, 1)
            self.assertEqual(result.verification_failed, 0)
            self.assertEqual(result.errors, 0)


    def test_no_temp_files_remain_after_successful_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "source.CR3"
            source_file.write_bytes(b"camera-file")
            destination_dir = root / "backup" / "2026" / "05" / "0503" / "cr3"

            result = execute_backup(
                [_make_item(source_file, destination_dir)],
                duplicate_policy="rename",
                dry_run=False,
                verify_mode="sha256",
            )

            self.assertEqual(result.copied, 1)
            leftovers = list(destination_dir.glob(f"*{TEMP_SUFFIX}"))
            self.assertEqual(leftovers, [])

    def test_failed_verification_preserves_existing_backup_on_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "source.CR3"
            source_file.write_bytes(b"new-content")

            destination_dir = root / "backup" / "2026" / "05" / "0503" / "cr3"
            destination_dir.mkdir(parents=True)
            existing = destination_dir / "source.CR3"
            existing.write_bytes(b"old-backup")

            with patch("src.backup_executor._verify_copy", return_value=False):
                result = execute_backup(
                    [_make_item(source_file, destination_dir)],
                    duplicate_policy="overwrite",
                    dry_run=False,
                    verify_mode="sha256",
                )

            self.assertEqual(result.copied, 0)
            self.assertEqual(result.overwritten, 0)
            self.assertEqual(result.verification_failed, 1)
            self.assertEqual(result.errors, 1)
            self.assertEqual(existing.read_bytes(), b"old-backup")
            leftovers = list(destination_dir.glob(f"*{TEMP_SUFFIX}"))
            self.assertEqual(leftovers, [])

    def test_failed_verification_leaves_no_final_file_for_new_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "source.CR3"
            source_file.write_bytes(b"camera-file")
            destination_dir = root / "backup" / "2026" / "05" / "0503" / "cr3"

            with patch("src.backup_executor._verify_copy", return_value=False):
                result = execute_backup(
                    [_make_item(source_file, destination_dir)],
                    duplicate_policy="rename",
                    dry_run=False,
                    verify_mode="size",
                )

            self.assertEqual(result.copied, 0)
            self.assertEqual(result.verification_failed, 1)
            self.assertFalse((destination_dir / "source.CR3").exists())
            leftovers = list(destination_dir.glob(f"*{TEMP_SUFFIX}"))
            self.assertEqual(leftovers, [])


    def test_smart_policy_skips_identical_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "source.CR3"
            source_file.write_bytes(b"same-content")

            destination_dir = root / "backup" / "2026" / "05" / "0503" / "cr3"
            destination_dir.mkdir(parents=True)
            (destination_dir / "source.CR3").write_bytes(b"same-content")

            result = execute_backup(
                [_make_item(source_file, destination_dir)],
                duplicate_policy="smart",
                dry_run=False,
            )

            self.assertEqual(result.copied, 0)
            self.assertEqual(result.skipped, 1)
            self.assertEqual(result.errors, 0)
            self.assertEqual(len(list(destination_dir.iterdir())), 1)

    def test_smart_policy_renames_when_content_differs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "source.CR3"
            source_file.write_bytes(b"new-different-content")

            destination_dir = root / "backup" / "2026" / "05" / "0503" / "cr3"
            destination_dir.mkdir(parents=True)
            (destination_dir / "source.CR3").write_bytes(b"old-content")

            result = execute_backup(
                [_make_item(source_file, destination_dir)],
                duplicate_policy="smart",
                dry_run=False,
            )

            self.assertEqual(result.copied, 1)
            self.assertEqual(result.skipped, 0)
            self.assertTrue((destination_dir / "source_001.CR3").exists())
            self.assertEqual(
                (destination_dir / "source.CR3").read_bytes(), b"old-content"
            )

    def test_smart_policy_finds_identical_in_renamed_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "source.CR3"
            source_file.write_bytes(b"same-content")

            destination_dir = root / "backup" / "2026" / "05" / "0503" / "cr3"
            destination_dir.mkdir(parents=True)
            (destination_dir / "source.CR3").write_bytes(b"different-base")
            (destination_dir / "source_001.CR3").write_bytes(b"same-content")

            result = execute_backup(
                [_make_item(source_file, destination_dir)],
                duplicate_policy="smart",
                dry_run=False,
            )

            self.assertEqual(result.copied, 0)
            self.assertEqual(result.skipped, 1)
            self.assertEqual(len(list(destination_dir.iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
