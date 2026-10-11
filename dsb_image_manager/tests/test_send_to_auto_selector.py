from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dsb_image_manager.dsb_image_manager.core.models import build_shots
from dsb_image_manager.dsb_image_manager.ui import tk_app
from dsb_image_manager.dsb_image_manager.ui.tk_app import ImageManagerApp


def _record(path: Path, media_type: str):
    return SimpleNamespace(
        file_path=path, media_type=media_type, pair_group_id=f"{path.parent}|{path.stem}".casefold(),
        pick_status="Pick", rating=0,
    )


class SendToAutoSelectorTests(unittest.TestCase):
    def _app(self, root: Path, records):
        shots = list(build_shots(records).values())
        catalog = SimpleNamespace(list_shots=lambda pick_filter="all": shots)
        status = SimpleNamespace(set=lambda text: self.statuses.append(text))
        return SimpleNamespace(catalog=catalog, source_dir=root, status=status, _can_start_work=lambda: True)

    def setUp(self):
        self.statuses = []

    def test_only_picked_jpgs_are_handed_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pick = root / "IMG_0001.jpg"
            pick.write_bytes(b"j")
            raw = root / "IMG_0001.CR3"
            raw.write_bytes(b"r")
            records = [
                _record(pick, "jpg"),
                _record(raw, "raw"),
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

    def test_picked_shots_without_a_jpg_are_counted_and_mentioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {}
            for name in ("A.jpg", "A.CR3", "B.CR3", "C.CR3"):
                files[name] = root / name
                files[name].write_bytes(b"x")
            app = self._app(root, [_record(path, "jpg" if path.suffix == ".jpg" else "raw") for path in files.values()])
            with patch("ndex_common.workflow.record_select_handoff", return_value=root / "h.json") as record,                     patch.object(tk_app.messagebox, "askyesno", return_value=True) as confirm,                     patch.object(tk_app, "launch_app", return_value=True):
                ImageManagerApp.send_to_auto_selector(app)
        self.assertEqual(record.call_args.args[1], [files["A.jpg"]])
        self.assertIn("2 picked shots have no JPG and will not be sent.",
                      confirm.call_args.args[1])
        self.assertEqual(self.statuses[-1], "Sent 1 picked JPG. 2 picked shots have no JPG and were not sent.")

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
