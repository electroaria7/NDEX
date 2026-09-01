from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common import crashlog


class CrashLogTests(unittest.TestCase):
    def tearDown(self) -> None:
        sys.excepthook = sys.__excepthook__
        threading.excepthook = threading.__excepthook__

    def test_write_crash_log_records_traceback_under_localappdata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
                path = crashlog.write_crash_log(
                    "NDEX Test",
                    ValueError,
                    ValueError("boom"),
                    None,
                )
            self.assertIsNotNone(path)
            assert path is not None
            text = path.read_text(encoding="utf-8")
            self.assertTrue(path.is_relative_to(Path(tmp) / "NDEX" / "logs"))
            self.assertIn("NDEX Test", text)
            self.assertIn("ValueError: boom", text)
            self.assertIn("NDEX ", text)
            self.assertIn("(beta)", text)

    def test_keyboard_interrupt_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": tmp}),
                patch.object(sys, "__excepthook__", lambda *_args: None),
            ):
                crashlog.install_crash_logging("NDEX Test")
                crashlog._handle_exception("NDEX Test", KeyboardInterrupt, KeyboardInterrupt(), None)
            logs = list(Path(tmp).rglob("crash_*.log"))
            self.assertEqual(logs, [])
