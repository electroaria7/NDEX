from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from dsb_image_manager.dsb_image_manager.core.models import ExportOptions
from dsb_image_manager.dsb_image_manager.services import backup, exporter, xmp_export
from dsb_image_manager.dsb_image_manager.services.catalog import Catalog
from dsb_image_manager.dsb_image_manager.services.scanner import ImageScanner
from dsb_image_manager.dsb_image_manager.ui import tk_app

from test_operation_lifecycle import FastMetadata, make_record


class TkOperationLifecycleTests(unittest.TestCase):
    """Real Tk event-loop checks, with all images/settings in a temporary folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "appdata")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.source = self.root / "source"
        for index in range(3):
            make_record(self.source / f"{index}.jpg", index)
        result = ImageScanner(FastMetadata()).scan(self.source)
        catalog = Catalog(result.catalog_path)
        catalog.update_selections([r.id for r in result.records], pick_status="Pick", rating=5)
        catalog.close()
        try:
            self.app = tk_app.ImageManagerApp()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.app.withdraw()
        self.destroyed = False
        self.app.bind("<Destroy>", self._on_destroy)
        self.addCleanup(self._cleanup_app)
        self.app.source_dir = self.source
        self.app._scan_finished(result.catalog_path)
        self.errors = []
        self.app.report_callback_exception = lambda kind, value, traceback: self.errors.append(value)
        self.info = patch.object(tk_app.messagebox, "showinfo").start()
        self.warning = patch.object(tk_app.messagebox, "showwarning").start()
        self.error = patch.object(tk_app.messagebox, "showerror").start()
        self.ask = patch.object(tk_app.messagebox, "askyesno", return_value=True).start()
        self.opened = patch.object(tk_app, "_open_folder").start()
        self.addCleanup(patch.stopall)

    def _on_destroy(self, event):
        if event.widget is self.app:
            self.destroyed = True

    def _cleanup_app(self):
        if not self.destroyed:
            self.app.destroy()
            self.pump_until(lambda: self.destroyed)

    def pump_until(self, condition, timeout=8):
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            self.app.update()
            time.sleep(0.005)
        self.assertTrue(condition(), "Tk event loop did not reach the expected state")
        self.assertEqual(self.errors, [])

    def test_backup_heartbeat_cancel_and_close_wait_for_verified_file_and_manifest(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = backup.copy_verified

        def slow_copy(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release copy")
            return original(*args, **kwargs)

        with patch.object(backup, "copy_verified", side_effect=slow_copy), \
                patch.object(tk_app.filedialog, "askdirectory", return_value=str(self.root / "backup")):
            self.app.backup_picked()
            self.pump_until(entered.is_set)
            worker = self.app._worker
            beats = []
            self.app.after(10, lambda: beats.append(True))
            self.pump_until(lambda: bool(beats))
            self.app.cancel_work()
            self.assertIn("current file", self.app.status.get())
            self.app.destroy()
            self.assertFalse(self.destroyed)
            self.assertTrue(worker.is_alive())
            release.set()
            self.pump_until(lambda: self.destroyed)
        self.assertFalse(worker.is_alive())
        report = self.root / "appdata" / "NDEX" / "manifests" / "latest-image_manager-backup.json"
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(payload["context"]["cancelled"])
        self.assertEqual(payload["counts"]["copied"], 1)
        self.assertEqual(payload["counts"]["failed"], 2)
        self.assertEqual(len(payload["items"]), 3)
        catalog = Catalog(self.source / ".dsb_cache" / "catalog.sqlite")
        self.assertEqual(sum(r.backup_status == "backed_up" for r in catalog.list_images()), 1)
        catalog.close()
        self.info.assert_not_called()
        self.warning.assert_not_called()

    def test_export_and_xmp_keep_tk_responsive_and_record_cancelled_sources(self):
        for kind, service, method in (("export", exporter, "copy_verified"),
                                      ("xmp", xmp_export, "write_xmp_sidecar")):
            with self.subTest(kind=kind):
                entered, release = threading.Event(), threading.Event()
                original = getattr(service, method)

                def slow_write(*args, **kwargs):
                    entered.set()
                    if not release.wait(5):
                        raise RuntimeError("Test did not release export")
                    return original(*args, **kwargs)

                try:
                    with patch.object(service, method, side_effect=slow_write):
                        if kind == "export":
                            dialog = Mock()
                            self.app._run_export(dialog, self.app.records, str(self.root / "out"), "{name}", "1", "rename")
                            dialog.destroy.assert_called_once()
                        else:
                            self.app.export_xmp_sidecars()
                        self.pump_until(entered.is_set)
                        beats = []
                        self.app.after(10, lambda: beats.append(True))
                        self.pump_until(lambda: bool(beats))
                        self.app.cancel_work()
                        release.set()
                        self.pump_until(lambda: self.app._active_job is None)
                finally:
                    release.set()
                payload = json.loads((self.root / "appdata" / "NDEX" / "manifests" /
                                      "latest-image_manager-export.json").read_text(encoding="utf-8"))
                self.assertEqual(payload["context"]["operation"], kind)
                self.assertTrue(payload["context"]["cancelled"])
                self.assertEqual(payload["counts"]["failed"], 2)
                self.assertEqual(len(payload["items"]), 3)

    def test_repeated_scan_is_serialized_and_cancelled_scan_preserves_picks(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        class SlowMetadata(FastMetadata):
            def read_batch(self, paths):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test did not release metadata")
                return {}

        # A new file forces a metadata read; unchanged files are reused without one.
        make_record(self.source / "new.jpg", 4)
        with patch.object(tk_app, "ImageScanner", return_value=ImageScanner(SlowMetadata())) as scanner:
            self.app.scan_folder()
            self.pump_until(entered.is_set)
            self.assertIsNone(self.app.catalog)
            first_worker = self.app._worker
            self.app.rescan()
            self.assertIs(self.app._worker, first_worker)
            self.assertEqual(scanner.call_count, 1)
            with patch.object(tk_app.filedialog, "askdirectory") as choose:
                self.app.choose_folder()
                choose.assert_not_called()
            self.app.refresh_records()
            self.assertEqual(self.app.records, [])
            self.app.cancel_work()
            release.set()
            self.pump_until(lambda: self.app._active_job is None)
        catalog = Catalog(self.source / ".dsb_cache" / "catalog.sqlite")
        self.assertEqual(len(catalog.list_images(pick_filter="Pick")), 3)
        catalog.close()
        with patch.object(tk_app, "ImageScanner", return_value=ImageScanner(FastMetadata())):
            self.app.scan_folder()
            self.pump_until(lambda: self.app._active_job is None)
        self.assertEqual(len(self.app.records), 4)
        self.assertEqual(sum(r.rating == 5 for r in self.app.records), 3)

    def test_queue_recovers_from_view_error_and_controls_fit_minimum_window(self):
        self.app.geometry("1040x680")
        self.app.attributes("-alpha", 0)
        self.app.deiconify()
        self.app.update_idletasks()
        self.pump_until(lambda: all(w.winfo_ismapped() for w in (
            self.app.choose_button, self.app.cancel_button, self.app.work_progress)))
        self.assertEqual(self.app.winfo_width(), 1040)
        for widget in (self.app.choose_button, self.app.cancel_button, self.app.work_progress):
            self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth())
            self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                 self.app.winfo_rootx() + self.app.winfo_width())
        self.app.withdraw()
        result = type("Result", (), {"catalog_path": self.source / ".dsb_cache" / "catalog.sqlite"})()
        self.app.ui_queue.put(("work_done", self.app._scan_generation, "scan", result, None, False))
        with patch.object(self.app, "_scan_finished", side_effect=OSError("catalog unavailable")):
            self.pump_until(lambda: self.error.called)
        self.assertIsNotNone(self.app._queue_job)
        self.assertIsNone(self.app._active_job)

    def test_closing_warns_if_report_could_not_be_saved(self):
        with patch("ndex_common.workflow.record_job", return_value=None):
            self.app._start_operation("export", self.app.records, self.root / "out",
                                      ExportOptions(self.root / "out", "{name}"))
            self.app.destroy()
            self.pump_until(lambda: self.destroyed)
        self.warning.assert_called_once()
        self.assertIn("Could not save Job Results", self.warning.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
