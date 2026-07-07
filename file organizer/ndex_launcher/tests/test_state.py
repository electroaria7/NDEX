from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_launcher import state as launcher_state


class LauncherStateTests(unittest.TestCase):
    def test_gather_state_with_empty_settings(self) -> None:
        with patch.object(launcher_state, "load_all", return_value={}):
            steps = launcher_state.gather_workflow_state()

        self.assertEqual([step.key for step in steps], ["ndex_one", "image_manager", "auto_selector"])
        self.assertEqual(steps[0].status_text, "No previous session")
        self.assertEqual(steps[1].launch_args, ["--open"])
        self.assertEqual(steps[2].launch_args, ["--open"])

    def test_gather_state_builds_handoff_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "backup"
            selects = Path(tmp) / "selects"
            raw = Path(tmp) / "raw"
            for folder in (backup, selects, raw):
                folder.mkdir()

            data = {
                "last_destination": str(backup),
                "auto_selector": {
                    "last_selected_jpg": str(selects),
                    "last_raw_source": str(raw),
                },
            }
            with patch.object(launcher_state, "load_all", return_value=data):
                steps = launcher_state.gather_workflow_state()

            self.assertTrue(steps[0].has_session)
            self.assertEqual(
                steps[1].launch_args, ["--open", "--source", str(backup)]
            )
            self.assertEqual(
                steps[2].launch_args,
                ["--open", "--selected-jpg", str(selects), "--raw-source", str(raw)],
            )

    def test_missing_folder_reported_in_status(self) -> None:
        data = {"last_destination": "Z:/definitely/not/here"}
        with patch.object(launcher_state, "load_all", return_value=data):
            steps = launcher_state.gather_workflow_state()

        self.assertFalse(steps[0].has_session)
        self.assertIn("missing", steps[0].status_text)


if __name__ == "__main__":
    unittest.main()
