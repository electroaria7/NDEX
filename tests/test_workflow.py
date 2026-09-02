from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ndex_common import manifest, session
from ndex_common.workflow import record_backup, record_export, record_select_handoff


class WorkflowRecordTests(unittest.TestCase):
    def _patch_roots(self, root: Path):
        settings_file = root / "config" / "settings.json"
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        return (
            patch("ndex_common.session.data_dir", return_value=root),
            patch("ndex_common.manifest.data_dir", return_value=root),
            patch("ndex_common.settings.data_dir", return_value=root),
            patch("ndex_common.settings.settings_path", return_value=settings_file),
            patch("ndex_common.settings._config_dir", return_value=settings_file.parent),
        )

    def test_select_handoff_writes_sidecar_and_frame_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root / "photos"
            photos.mkdir()
            pick = photos / "pick.jpg"
            pick.write_bytes(b"jpg")
            patches = self._patch_roots(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                path = record_select_handoff(photos, [pick])
                loaded = manifest.load_manifest(path)
                frame = session.load_session("frame", root=root)
                stored = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))

            self.assertIsNotNone(path)
            assert path is not None
            self.assertTrue(path.is_file())
            self.assertEqual(path.parent.resolve(), (root / "manifests").resolve())
            self.assertEqual(loaded["type"], "select_handoff")
            self.assertEqual(loaded["items"][0]["path"], str(pick))
            self.assertFalse(any(photos.glob("*.json")))
            self.assertEqual(frame["context"]["handoff"], str(path))
            self.assertNotIn("files", stored["shared"]["sessions"]["image_manager"]["context"])
            self.assertEqual(stored["schema_version"], 1)

    def test_backup_and_export_count_copied_skipped_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self._patch_roots(root)
            backup_result = SimpleNamespace(
                copied=2,
                skipped=1,
                errors=0,
                overwritten=0,
                cancelled=False,
                messages=["copied a"],
                items=[{"path": "a.CR3", "status": "copied"}],
            )
            export_result = SimpleNamespace(
                exported=1,
                skipped=0,
                failed=1,
                cancelled=False,
                items=[
                    SimpleNamespace(source="in.jpg", destination="out.jpg", state="exported", message=""),
                    SimpleNamespace(source="bad.jpg", destination="", state="failed", message="boom"),
                ],
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                backup = record_backup("E:/DCIM", "D:/Lib", backup_result)
                export = record_export("D:/Masters", "D:/Framed", export_result, frame_preset="builtin.white-3x4")
                backup_doc = manifest.load_manifest(backup)
                export_doc = manifest.load_manifest(export)

            self.assertEqual(backup_doc["counts"]["copied"], 2)
            self.assertEqual(backup_doc["counts"]["skipped"], 1)
            self.assertEqual(export_doc["counts"]["failed"], 1)
            self.assertEqual(export_doc["context"]["frame_preset"], "builtin.white-3x4")


if __name__ == "__main__":
    unittest.main()
