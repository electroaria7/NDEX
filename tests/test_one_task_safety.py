from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.backup_executor import execute_backup
from src.gui import DSBApp
from src.models import ScanItem
from src.scanner import collect_supported_files


class BackupCollisionTests(unittest.TestCase):
    def test_non_overwrite_preserves_destination_claimed_during_copy(self):
        for policy in ("rename", "skip", "smart"):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "photo.JPG"
                source.write_bytes(b"camera")
                destination = root / "backup"
                item = ScanItem(source, "jpg", datetime(2026, 10, 10), "test", destination)
                real_copy = shutil.copy2

                def concurrent_copy(src, temp):
                    real_copy(src, temp)
                    (destination / source.name).write_bytes(b"other backup")

                with patch("src.backup_executor.shutil.copy2", side_effect=concurrent_copy):
                    result = execute_backup([item], duplicate_policy=policy)
                self.assertEqual((destination / source.name).read_bytes(), b"other backup")
                self.assertEqual(result.copied, 0)
                self.assertEqual(result.errors, 1)
                self.assertEqual(list(destination.glob("*.ndex_tmp")), [])

    def test_excluded_backup_directory_is_not_traversed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = root / "backup"
            (backup / "deep").mkdir(parents=True)
            (root / "photo.JPG").write_bytes(b"camera")
            (backup / "deep" / "old.JPG").write_bytes(b"old")
            visited = []
            real_scandir = os.scandir

            def track(path):
                visited.append(Path(path))
                return real_scandir(path)

            with patch("src.scanner.os.scandir", side_effect=track):
                result = collect_supported_files(root, ["jpg"], backup)
            self.assertEqual(result, [root / "photo.JPG"])
            self.assertNotIn(backup, visited)
            self.assertNotIn(backup / "deep", visited)


class OneTaskLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "appdata")})
        env.start()
        self.addCleanup(env.stop)
        self.app = DSBApp(preload_only=True)
        self.app.withdraw()
        self.addCleanup(self._destroy)

    def _destroy(self):
        thread = self.app.worker_thread
        if thread and thread.is_alive():
            self.app.cancel_event.set()
            thread.join(5)
        try:
            for timer in self.app.tk.call("after", "info"):
                self.app.after_cancel(timer)
            self.app.destroy()
        except Exception:
            pass

    def _pump_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.005)
        self.assertTrue(predicate())

    def test_plan_invalidates_when_paths_or_file_types_change(self):
        for variable, value in ((self.app.destination_var, "elsewhere"),
                                (self.app.source_var, "another"),
                                (self.app.type_vars["jpg"], False)):
            self.app.current_summary = object()
            variable.set(value)
            self.assertIsNone(self.app.current_summary)
            self.assertEqual(str(self.app.backup_button["state"]), "disabled")

    def test_close_keeps_event_loop_alive_until_worker_and_record_finish(self):
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        self.addCleanup(release.set)

        def worker():
            entered.set()
            release.wait(3)
            finished.set()
            self.app.ui_queue.put(("backup_done", result))

        from src.models import BackupResult
        result = BackupResult(total=0, cancelled=True)
        self.app._set_busy(True, "Working")
        self.app._run_worker(worker)
        self.assertTrue(entered.wait(1))
        self.assertFalse(self.app.worker_thread.daemon)
        with patch("src.gui.messagebox.askyesno", return_value=True), patch.object(self.app, "destroy") as destroy:
            self.app._request_close()
            self.assertTrue(self.app.cancel_event.is_set())
            pulse = []
            self.app.after(0, lambda: pulse.append(True))
            self._pump_until(lambda: bool(pulse))
            destroy.assert_not_called()
            release.set()
            self._pump_until(lambda: destroy.called)
            self.assertTrue(finished.is_set())
            self.assertFalse(self.app.worker_thread.is_alive())

    def test_recording_runs_in_worker_before_completion_is_delivered(self):
        from src.models import BackupResult
        while not self.app.ui_queue.empty():
            self.app.ui_queue.get_nowait()
        self.app.pending_backup = {
            "items": [], "source": "card", "destination": "backup", "retry": None,
            "duplicate_policy": "rename", "dry_run": False, "verify_mode": "size",
        }
        result = BackupResult(total=0)
        thread_ids = []

        def record(_result):
            thread_ids.append(threading.get_ident())
            self.assertTrue(self.app.ui_queue.empty())
            return self.root / "manifest.json"

        with patch("src.gui.execute_backup", return_value=result), patch.object(self.app, "_record_backup_session", side_effect=record):
            self.app._run_worker(self.app._backup_worker)
            self.app.worker_thread.join(2)
        self.assertNotEqual(thread_ids, [threading.get_ident()])
        self.assertEqual(self.app.ui_queue.get_nowait()[0], "backup_done")

    def test_busy_controls_keep_readonly_comboboxes_after_unlock(self):
        from tkinter import ttk
        self.app._set_busy(True, "Working")
        self.assertTrue(all(control.instate(["disabled"]) for control in self.app._input_controls))
        self.app._set_busy(False, "Done")
        combos = [control for control in self.app._input_controls if isinstance(control, ttk.Combobox)]
        self.assertEqual(len(combos), 2)
        self.assertTrue(all(control.instate(["readonly", "!disabled"]) for control in combos))


if __name__ == "__main__":
    unittest.main()
