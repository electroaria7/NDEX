from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common import manifest


class ManifestTests(unittest.TestCase):
    def test_write_and_load_backup_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = manifest.write_manifest(
                type="backup",
                app="ndex_one",
                source="E:/DCIM",
                destination="D:/Lib",
                counts={"copied": 2, "skipped": 1, "failed": 0},
                items=[
                    {"path": "E:/DCIM/IMG_0001.CR3", "status": "copied"},
                    {"path": "E:/DCIM/IMG_0002.JPG", "status": "skipped", "detail": "exists"},
                ],
                root=root,
            )
            loaded = manifest.load_manifest(path)
            latest = manifest.load_manifest(root / "manifests" / "latest-ndex_one-backup.json")

            self.assertTrue(path.is_file())
            self.assertEqual(loaded["kind"], manifest.KIND)
            self.assertEqual(loaded["counts"]["copied"], 2)
            self.assertEqual(loaded["items"][1]["status"], "skipped")
            self.assertEqual(latest["destination"], "D:/Lib")

    def test_frame_ready_paths_keep_supported_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jpg = root / "pick.JPG"
            raw = root / "pick.CR3"
            missing = root / "gone.png"
            jpg.write_bytes(b"jpg")
            raw.write_bytes(b"raw")
            ready = manifest.frame_ready_paths([jpg, raw, missing, jpg])
            self.assertEqual(ready, [jpg])

    def test_handoff_files_read_items_and_files_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "a.jpg"
            two = root / "b.png"
            one.write_bytes(b"a")
            two.write_bytes(b"b")
            payload = {
                "kind": manifest.KIND,
                "type": "select_handoff",
                "files": [str(one)],
                "items": [{"path": str(two), "status": "selected"}],
            }
            files = manifest.handoff_files(payload)
            self.assertEqual(files, [one, two])

    def test_same_second_jobs_do_not_overwrite_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stamp = "20260902T101500Z"
            with patch.object(manifest, "datetime") as clock:
                clock.now.return_value.strftime.side_effect = lambda fmt: (
                    stamp if "%Y%m%dT" in fmt else "2026-09-02T10:15:00Z"
                )
                first = manifest.write_manifest(type="backup", app="ndex_one", source="A", root=root)
                second = manifest.write_manifest(type="backup", app="ndex_one", source="B", root=root)

            self.assertNotEqual(first, second)
            self.assertEqual(manifest.load_manifest(first)["source"], "A")
            self.assertEqual(manifest.load_manifest(second)["source"], "B")

    def test_rejects_unknown_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                manifest.write_manifest(type="nope", app="frame", root=Path(tmp))


if __name__ == "__main__":
    unittest.main()
