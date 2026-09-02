from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common.report import JobReport
from ndex_launcher import state as launcher_state


def _write_handoff(folder: Path) -> Path:
    """A select-handoff manifest whose listed file still exists."""
    picked = folder / "pick.jpg"
    picked.write_bytes(b"jpg")
    handoff = folder / "select-handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "kind": "ndex.manifest",
                "schema_version": 1,
                "type": "select_handoff",
                "app": "image_manager",
                "items": [{"path": str(picked), "status": "selected"}],
            }
        ),
        encoding="utf-8",
    )
    return handoff


def _report(app: str, type: str, created_at: str, counts: dict) -> JobReport:
    return JobReport(
        manifest_path=Path(f"{type}-{created_at}.json"),
        type=type,
        app=app,
        created_at=created_at,
        counts=counts,
    )


class LauncherStateTests(unittest.TestCase):
    def test_gather_state_with_empty_settings(self) -> None:
        with patch.object(launcher_state, "load_all", return_value={}):
            steps = launcher_state.gather_workflow_state()

        self.assertEqual(
            [step.key for step in steps],
            ["ndex_one", "image_manager", "auto_selector", "frame"],
        )
        self.assertEqual(steps[0].status_text, "No previous session")
        self.assertEqual(steps[1].launch_args, ["--open"])
        self.assertEqual(steps[2].launch_args, ["--open"])
        self.assertEqual(steps[3].launch_args, ["--open"])
        self.assertEqual(steps[3].title, "4. Frame & Export - NDEX Frame")

    def test_gather_state_builds_handoff_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "backup"
            selects = Path(tmp) / "selects"
            raw = Path(tmp) / "raw"
            masters = Path(tmp) / "masters"
            for folder in (backup, selects, raw, masters):
                folder.mkdir()

            data = {
                "last_destination": str(backup),
                "auto_selector": {
                    "last_selected_jpg": str(selects),
                    "last_raw_source": str(raw),
                },
                "frame": {"last_source": str(masters)},
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
            self.assertEqual(
                steps[3].launch_args, ["--open", "--source", str(masters)]
            )

    def test_frame_continue_prefers_handoff_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = _write_handoff(Path(tmp))
            data = {
                "shared": {
                    "sessions": {
                        "frame": {
                            "kind": "ndex.session",
                            "app": "frame",
                            "folders": {"source": "Z:/gone"},
                            "last_manifest": str(handoff),
                            "context": {"handoff": str(handoff)},
                        }
                    }
                }
            }
            with patch.object(launcher_state, "load_all", return_value=data):
                steps = launcher_state.gather_workflow_state()

        self.assertTrue(steps[3].has_session)
        self.assertEqual(steps[3].launch_args[:3], ["--open", "--handoff", str(handoff)])
        self.assertEqual(steps[3].status_text, f"Last handoff: {handoff}")

    def test_frame_status_reports_missing_folder_when_handoff_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp) / "select-handoff.json"
            handoff.write_text("{}", encoding="utf-8")
            data = {
                "shared": {
                    "sessions": {
                        "frame": {
                            "kind": "ndex.session",
                            "app": "frame",
                            "folders": {"source": "Z:/gone"},
                            "context": {"handoff": str(handoff)},
                        }
                    }
                }
            }
            with patch.object(launcher_state, "load_all", return_value=data):
                steps = launcher_state.gather_workflow_state()

        self.assertFalse(steps[3].has_session)
        self.assertEqual(steps[3].launch_args, ["--open"])
        self.assertIn("missing", steps[3].status_text)

    def test_frame_launch_skips_missing_source_folder(self) -> None:
        data = {"frame": {"last_source": "Z:/definitely/not/here"}}
        with patch.object(launcher_state, "load_all", return_value=data):
            steps = launcher_state.gather_workflow_state()

        self.assertEqual(steps[3].key, "frame")
        self.assertFalse(steps[3].has_session)
        self.assertEqual(steps[3].launch_args, ["--open"])
        self.assertIn("missing", steps[3].status_text)

    def test_cards_show_the_latest_job_per_app(self) -> None:
        backup = _report("ndex_one", "backup", "2026-09-01T09:00:00Z", {"copied": 10})
        newer_backup = _report("ndex_one", "backup", "2026-09-02T10:15:00Z", {"copied": 42, "failed": 1})
        export = _report("frame", "export", "2026-09-02T11:00:00Z", {"copied": 5})

        with (
            patch.object(launcher_state, "load_all", return_value={}),
            patch(
                "ndex_common.report.iter_reports",
                return_value=iter([export, newer_backup, backup]),
            ),
        ):
            steps = launcher_state.gather_workflow_state()

        self.assertEqual(steps[0].last_result, newer_backup)
        self.assertIn("42 copied, 1 failed", steps[0].result_text)
        self.assertIn("5 copied", steps[3].result_text)
        self.assertEqual(steps[1].result_text, "No job results yet")

    def test_frame_app_command_is_registered(self) -> None:
        from ndex_common.launch import APP_COMMANDS, _DIST_SUBDIRS

        self.assertEqual(APP_COMMANDS["frame"], ("NDEX_Frame.exe", "ndex_frame.main"))
        self.assertIn("ndex_frame/dist", _DIST_SUBDIRS)

    def test_missing_folder_reported_in_status(self) -> None:
        data = {"last_destination": "Z:/definitely/not/here"}
        with patch.object(launcher_state, "load_all", return_value=data):
            steps = launcher_state.gather_workflow_state()

        self.assertFalse(steps[0].has_session)
        self.assertIn("missing", steps[0].status_text)


if __name__ == "__main__":
    unittest.main()
