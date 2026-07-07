from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.scanner import analyze_source


class FakeMetadataExtractor:
    def __init__(self):
        self.batch_used = False

    def get_capture_datetimes(self, file_paths, logger=None):
        self.batch_used = True
        return {
            file_path: (datetime(2026, 5, 3, 9, 0, 0), "fake_batch", False)
            for file_path in file_paths
        }

    def get_capture_datetime(self, file_path, logger=None):
        return datetime(2026, 5, 3, 9, 0, 0), "fake", False


class ScannerTests(unittest.TestCase):
    def test_analyze_source_counts_supported_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            backup = root / "backup"
            source.mkdir()
            backup.mkdir()
            (source / "IMG_0001.CR3").write_text("cr3", encoding="utf-8")
            (source / "IMG_0002.JPG").write_text("jpg", encoding="utf-8")
            (source / "IMG_0003.CR2").write_text("cr2", encoding="utf-8")
            (source / "IMG_0004.ARW").write_text("arw", encoding="utf-8")
            (source / "IMG_0005.NEF").write_text("nef", encoding="utf-8")
            (source / "note.txt").write_text("ignore", encoding="utf-8")

            extractor = FakeMetadataExtractor()
            summary = analyze_source(
                source_dir=source,
                backup_root=backup,
                metadata_extractor=extractor,
                enabled_types=["cr3", "cr2", "arw", "nef", "jpg"],
            )

            self.assertEqual(summary.counts["cr3"], 1)
            self.assertEqual(summary.counts["cr2"], 1)
            self.assertEqual(summary.counts["arw"], 1)
            self.assertEqual(summary.counts["nef"], 1)
            self.assertEqual(summary.counts["jpg"], 1)
            self.assertEqual(len(summary.items), 5)
            self.assertEqual(len(summary.preview_rows), 1)
            self.assertTrue(extractor.batch_used)


if __name__ == "__main__":
    unittest.main()
