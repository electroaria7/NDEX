from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dsb_image_manager.dsb_image_manager.ui import tk_app
from dsb_image_manager.dsb_image_manager.ui.tk_app import ImageManagerApp


class SendToAutoSelectorTests(unittest.TestCase):
    def _app(self, root: Path, records):
        catalog = SimpleNamespace(list_images=lambda pick_filter=None: records)
        return SimpleNamespace(catalog=catalog, source_dir=root, _can_start_work=lambda: True)

    def test_only_picked_jpgs_are_handed_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pick = root / "IMG_0001.jpg"
            pick.write_bytes(b"j")
            raw = root / "IMG_0001.CR3"
            raw.write_bytes(b"r")
            records = [
                SimpleNamespace(file_path=pick, media_type="jpg"),
                SimpleNamespace(file_path=raw, media_type="raw"),
            ]
            app = self._app(root, records)
            with patch("ndex_common.workflow.record_select_handoff", return_value=root / "h.json") as record, \
                    patch.object(tk_app.messagebox, "askyesno", return_value=True) as confirm, \
                    patch.object(tk_app, "launch_app", return_value=True) as launch:
                ImageManagerApp.send_to_auto_selector(app)
        self.assertEqual(record.call_args.args[1], [pick])
        self.assertIn("Send 1 picked JPG to Auto Selector?", confirm.call_args.args[1])
        self.assertEqual(
            launch.call_args.args,
            ("auto_selector", ["--open", "--handoff", str(root / "h.json"), "--raw-source", str(root)]),
        )

    def test_no_picks_shows_message_and_does_not_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp), [])
            with patch.object(tk_app, "launch_app") as launch, \
                    patch.object(tk_app.messagebox, "showinfo") as info:
                ImageManagerApp.send_to_auto_selector(app)
        info.assert_called_once()
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
