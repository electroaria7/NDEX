from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.folder_manager import build_destination_dir, resolve_duplicate_path


class FolderManagerTests(unittest.TestCase):
    def test_build_destination_dir_uses_date_layout(self):
        destination = build_destination_dir(
            Path("D:/PhotoBackup"),
            datetime(2026, 5, 3, 14, 30, 0),
            "cr3",
        )
        self.assertEqual(destination.as_posix(), "D:/PhotoBackup/2026/05/0503/cr3")

    def test_resolve_duplicate_path_appends_counter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "IMG_0001.CR3"
            base.write_text("first", encoding="utf-8")
            duplicate = resolve_duplicate_path(base)
            self.assertEqual(duplicate.name, "IMG_0001_001.CR3")


if __name__ == "__main__":
    unittest.main()
