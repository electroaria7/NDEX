from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ndex_common import manifest, session
from ndex_common.report import JobReport
from ndex_common.workflow import record_select_handoff

from test_workflow import patch_roots


class HandoffTargetTests(unittest.TestCase):
    def _record(self, root: Path, **kwargs) -> Path:
        photos = root / "photos"
        photos.mkdir(exist_ok=True)
        pick = photos / "pick.jpg"
        pick.write_bytes(b"jpg")
        patches = patch_roots(root)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            path = record_select_handoff(photos, [pick], **kwargs)
        self.assertIsNotNone(path)
        return path

    def test_auto_selector_handoff_does_not_become_frames_continue_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._record(root, target="auto_selector")
            frame = session.load_session("frame", root=root)
            self.assertFalse((frame or {}).get("context", {}).get("handoff"))
            payload = manifest.load_manifest(path)
            self.assertEqual(payload["context"]["target"], "auto_selector")

    def test_frame_handoff_still_sets_frames_continue_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._record(root)
            frame = session.load_session("frame", root=root)
            self.assertEqual(frame["context"]["handoff"], str(path))

    def test_type_label_names_the_receiving_app(self) -> None:
        to_selector = JobReport(
            manifest_path=Path("m.json"), type="select_handoff", app="image_manager",
            created_at="", context={"target": "auto_selector"},
        )
        to_frame = JobReport(
            manifest_path=Path("m.json"), type="select_handoff", app="image_manager", created_at="",
        )
        self.assertEqual(to_selector.type_label, "Send to Auto Selector")
        self.assertEqual(to_frame.type_label, "Send to Frame")


if __name__ == "__main__":
    unittest.main()
