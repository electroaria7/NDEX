from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common import session
from ndex_common.settings import migrate


class SessionDocumentTests(unittest.TestCase):
    def test_remember_writes_file_and_shared_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings_file = root / "config" / "settings.json"
            settings_file.parent.mkdir()
            with (
                patch("ndex_common.session.data_dir", return_value=root),
                patch("ndex_common.settings.settings_path", return_value=settings_file),
                patch("ndex_common.settings._config_dir", return_value=settings_file.parent),
            ):
                document = session.remember(
                    "ndex_one",
                    folders={"source": "D:/Card", "destination": "D:/Lib"},
                    last_manifest="D:/Lib/backup.json",
                    root=root,
                )
                loaded = session.load_session("ndex_one", root=root)
                stored = json.loads(settings_file.read_text(encoding="utf-8"))

            self.assertEqual(document["kind"], session.KIND)
            self.assertEqual(loaded["folders"]["destination"], "D:/Lib")
            self.assertEqual(stored["shared"]["sessions"]["ndex_one"]["last_manifest"], "D:/Lib/backup.json")
            self.assertEqual(stored["schema_version"], 1)

    def test_hydrate_from_legacy_settings_without_session_file(self) -> None:
        data = {
            "last_destination": "D:/Backup",
            "image_manager": {"last_source": "D:/Shoot"},
            "auto_selector": {
                "last_selected_jpg": "D:/Selects",
                "last_raw_source": "D:/RAW",
                "last_work_folder": "D:/Work",
            },
            "frame": {"last_source": "D:/Masters"},
        }
        one = session.session_from_settings(data, "ndex_one")
        manager = session.session_from_settings(data, "image_manager")
        selector = session.session_from_settings(data, "auto_selector")
        frame = session.session_from_settings(data, "frame")
        self.assertEqual(one["folders"]["destination"], "D:/Backup")
        self.assertEqual(manager["folders"]["source"], "D:/Shoot")
        self.assertEqual(selector["folders"]["work"], "D:/Work")
        self.assertEqual(frame["folders"]["source"], "D:/Masters")

    def test_launch_args_omit_missing_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            present = Path(tmp) / "masters"
            present.mkdir()
            document = session.empty_session("frame")
            document["folders"] = {"source": str(present), "output": "Z:/missing-output"}
            args = session.launch_args(document)
        self.assertEqual(args, ["--open", "--source", str(present)])

    def test_frame_continue_prefers_handoff_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp) / "select-to-frame.json"
            handoff.write_text("{}", encoding="utf-8")
            document = session.empty_session("frame")
            document["context"] = {"handoff": str(handoff)}
            document["folders"] = {"source": "Z:/also-missing"}
            args = session.launch_args(document)
        self.assertEqual(args[:3], ["--open", "--handoff", str(handoff)])

    def test_missing_context_falls_back_to_open(self) -> None:
        document = session.session_from_settings({"last_destination": "Z:/gone"}, "ndex_one")
        self.assertFalse(session.usable(document))
        self.assertEqual(session.launch_args(document), ["--open"])
        self.assertEqual(session.preferred_folder(document), "Z:/gone")

    def test_settings_migration_keeps_shared_sessions(self) -> None:
        migrated = migrate(
            {"schema_version": 1, "shared": {"sessions": {"frame": {"app": "frame", "folders": {}}}}}
        )
        self.assertEqual(migrated["schema_version"], 1)
        self.assertIn("sessions", migrated["shared"])


if __name__ == "__main__":
    unittest.main()
