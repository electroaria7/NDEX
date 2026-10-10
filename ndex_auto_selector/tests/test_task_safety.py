from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ndex_auto_selector.ndex_auto_selector.services import selector
from ndex_auto_selector.ndex_auto_selector.ui.tk_app import AutoSelectorApp


def make_folders(root: Path, count: int = 3):
    raw, jpg, work = root / "raw", root / "jpg", root / "work"
    for folder in (raw, jpg, work):
        folder.mkdir()
    for index in range(count):
        (raw / f"IMG_{index:04}.CR3").write_bytes(f"raw {index}".encode())
        (jpg / f"IMG_{index:04}.jpg").write_bytes(b"selected")
    return raw, jpg, work


class ServiceTaskSafetyTests(unittest.TestCase):
    def test_cancel_finishes_current_file_and_records_every_remaining_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = make_folders(Path(tmp))
            service = selector.AutoSelectorService()
            matches = service.analyze(raw, jpg).matches
            cancel = threading.Event()
            result = service.copy_matches(
                matches, work, write_xmp=True, cancel_event=cancel,
                progress_callback=lambda *_: cancel.set(),
            )
            self.assertTrue(result.cancelled)
            self.assertEqual((result.total, result.copied, result.xmp_written, result.errors), (3, 1, 1, 2))
            self.assertEqual((work / "IMG_0000.CR3").read_bytes(), b"raw 0")
            self.assertTrue((work / "IMG_0000.xmp").is_file())
            self.assertFalse((work / "IMG_0001.CR3").exists())
            self.assertEqual(result.items[1:], [
                {"path": str(match.jpg_path), "status": "failed", "detail": "not run: cancelled"}
                for match in matches[1:]
            ])
            self.assertEqual(list(work.glob("*.ndex_tmp")), [])

    def test_cancelled_analysis_does_not_return_a_partial_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, _ = make_folders(Path(tmp))
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(selector.AnalysisCancelled):
                selector.AutoSelectorService().analyze(raw, jpg, cancel_event=cancel)

    def test_rename_retry_recovers_xmp_without_creating_another_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = make_folders(Path(tmp), count=1)
            (work / "IMG_0000.CR3").write_bytes(b"old unrelated raw")
            service = selector.AutoSelectorService()
            matches = service.analyze(raw, jpg).matches
            with patch.object(service, "_write_selected_xmp", side_effect=OSError("disk full")):
                first = service.copy_matches(matches, work, write_xmp=True)
            again = service.copy_matches(matches, work, write_xmp=True)
            self.assertEqual(first.errors, 1)
            self.assertEqual((again.copied, again.skipped, again.xmp_written, again.errors), (0, 1, 1, 0))
            self.assertEqual(sorted(path.name for path in work.glob("*.CR3")),
                             ["IMG_0000.CR3", "IMG_0000_001.CR3"])
            self.assertTrue((work / "IMG_0000_001.xmp").exists())
            self.assertEqual((work / "IMG_0000.CR3").read_bytes(), b"old unrelated raw")

    def test_rename_finds_identical_copy_beyond_a_numbering_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = make_folders(Path(tmp), count=1)
            (work / "IMG_0000.CR3").write_bytes(b"unrelated")
            (work / "IMG_0000_002.CR3").write_bytes(b"raw 0")
            service = selector.AutoSelectorService()
            result = service.copy_matches(service.analyze(raw, jpg).matches, work)
            self.assertEqual((result.copied, result.skipped), (0, 1))
            self.assertFalse((work / "IMG_0000_001.CR3").exists())

    def test_scan_prunes_work_and_cache_before_opening_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, _ = make_folders(Path(tmp), count=1)
            work = raw / "work"
            cache = jpg / ".DSB_CACHE"
            for folder in (work / "deep", cache / "deep"):
                folder.mkdir(parents=True)
            (work / "deep" / "IMG_0000.CR3").write_bytes(b"copied raw")
            (cache / "deep" / "IMG_0000.jpg").write_bytes(b"thumbnail")
            scanned = []
            real_scandir = os.scandir

            def observe(path):
                scanned.append(Path(path))
                return real_scandir(path)

            with patch.object(selector.os, "scandir", side_effect=observe):
                summary = selector.AutoSelectorService().analyze(raw, jpg, exclude=work)
            self.assertEqual((summary.selected_count, summary.matched_count), (1, 1))
            self.assertNotIn(work, scanned)
            self.assertNotIn(cache, scanned)
            self.assertFalse(any(work in path.parents or cache in path.parents for path in scanned))


class TkTaskSafetyTests(unittest.TestCase):
    """Exercise the real Tk event loop while a controlled worker remains busy."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ndex-selector-ui-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw, self.jpg, self.work = make_folders(self.root)
        self.environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "appdata")})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.settings = patch("ndex_auto_selector.ndex_auto_selector.ui.tk_app.get_section", return_value={})
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.app = AutoSelectorApp(self.raw, self.jpg, self.work)
        self.app.withdraw()
        self.addCleanup(self._cleanup_app)

    def _cleanup_app(self):
        self.app.cancel_event.set()
        if self.app.worker_thread is not None:
            self.app.worker_thread.join(timeout=4)
        if not self.app._closed:
            self.app._on_close()
            self._pump_until(lambda: self.app._closed)

    def _pump_until(self, condition, timeout=4):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            if not self.app._closed:
                self.app.update()
            time.sleep(0.005)
        self.assertTrue(condition(), "Tk worker/event loop did not finish before timeout")

    def _ready_for_copy(self):
        self.app.summary = self.app.service.analyze(self.raw, self.jpg, exclude=self.work)
        self.app._analysis_context = self.app._current_analysis_context()
        self.app._update_buttons()

    def test_analysis_keeps_tk_responsive_and_cancel_restores_inputs(self):
        entered = threading.Event()

        def analyze(*args, cancel_event, **kwargs):
            entered.set()
            if cancel_event.wait(3):
                raise selector.AnalysisCancelled()
            raise AssertionError("Test analysis was not cancelled")

        heartbeat = []
        with patch.object(self.app.service, "analyze", side_effect=analyze):
            self.app.start_analysis()
            self._pump_until(entered.is_set)
            self.assertTrue(all(str(widget.cget("state")) == "disabled"
                                for widget, _ in self.app._input_widgets))
            self.assertEqual(str(self.app.progress_bar.cget("mode")), "indeterminate")
            self.app.after(5, lambda: heartbeat.append(True))
            self._pump_until(lambda: bool(heartbeat))
            self.assertTrue(self.app.worker_thread.is_alive())
            self.app.cancel_work()
            self._pump_until(lambda: not self.app._busy)
        self.assertIsNone(self.app.summary)
        self.assertTrue(all(str(widget.cget("state")) == state
                            for widget, state in self.app._input_widgets))
        self.assertEqual(str(self.app.copy_button.cget("state")), "disabled")

    def test_changed_analysis_inputs_discard_the_inflight_result(self):
        entered, release = threading.Event(), threading.Event()
        real_analyze = self.app.service.analyze

        def analyze(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError("Test analysis was not released")
            return real_analyze(*args, **kwargs)

        with patch.object(self.app.service, "analyze", side_effect=analyze):
            self.app.start_analysis()
            self._pump_until(entered.is_set)
            self.app.recursive_var.set(False)
            release.set()
            self._pump_until(lambda: not self.app._busy)
        self.assertIsNone(self.app.summary)
        self.assertEqual(str(self.app.copy_button.cget("state")), "disabled")

    def test_work_folder_and_recursive_changes_invalidate_completed_analysis(self):
        for change in (lambda: self.app.recursive_var.set(False),
                       lambda: self.app.work_folder_var.set(str(self.root / "another"))):
            self._ready_for_copy()
            self.assertEqual(str(self.app.copy_button.cget("state")), "normal")
            change()
            self.assertIsNone(self.app.summary)
            self.assertEqual(str(self.app.copy_button.cget("state")), "disabled")

    def test_close_waits_for_current_copy_and_records_unprocessed_files(self):
        self._ready_for_copy()
        entered, release = threading.Event(), threading.Event()
        real_copy = selector.copy_verified
        records = []

        def copy(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError("Test copy was not released")
            return real_copy(*args, **kwargs)

        def record(*args, **kwargs):
            self.assertFalse(self.app._closed)
            records.append((args, kwargs))
            return self.root / "record.json"

        with patch.object(selector, "copy_verified", side_effect=copy), \
                patch.object(self.app, "_save_settings"), \
                patch("ndex_common.workflow.record_extract", side_effect=record):
            self.app.start_copy()
            self._pump_until(entered.is_set)
            self.app._on_close()
            heartbeat = []
            self.app.after(5, lambda: heartbeat.append(True))
            self._pump_until(lambda: bool(heartbeat))
            self.assertFalse(self.app._closed)
            self.assertTrue(self.app.worker_thread.is_alive())
            release.set()
            self._pump_until(lambda: self.app._closed)
        self.assertEqual(len(records), 1)
        result = records[0][0][3]
        self.assertEqual((result.copied, result.errors, result.cancelled), (1, 2, True))
        self.assertFalse(self.app.worker_thread.is_alive())
        self.assertEqual((self.work / "IMG_0000.CR3").read_bytes(), b"raw 0")
        self.assertFalse((self.work / "IMG_0001.CR3").exists())

    def test_copy_worker_uses_snapshot_after_form_summary_is_invalidated(self):
        self._ready_for_copy()
        entered, release = threading.Event(), threading.Event()
        real_worker = self.app._copy_worker

        def worker(job):
            entered.set()
            if release.wait(3):
                real_worker(job)

        with patch.object(self.app, "_copy_worker", side_effect=worker), \
                patch.object(self.app, "_save_settings"), \
                patch("ndex_common.workflow.record_extract") as record:
            self.app.start_copy()
            self._pump_until(entered.is_set)
            self.app.summary = None
            release.set()
            self._pump_until(lambda: not self.app._busy)
        self.assertEqual(record.call_args.args[3].copied, 3)
        self.assertEqual(len(list(self.work.glob("*.CR3"))), 3)

    def test_recording_lock_does_not_block_tk_or_allow_early_close(self):
        self._ready_for_copy()
        entered, release = threading.Event(), threading.Event()

        def record(*args, **kwargs):
            self.assertNotEqual(threading.current_thread(), threading.main_thread())
            entered.set()
            if not release.wait(3):
                raise AssertionError("Test recording lock was not released")
            return self.root / "record.json"

        with patch.object(self.app, "_save_settings"), \
                patch("ndex_common.workflow.record_extract", side_effect=record):
            self.app.start_copy()
            self._pump_until(entered.is_set)
            self.app._on_close()
            heartbeat = []
            self.app.after(5, lambda: heartbeat.append(True))
            self._pump_until(lambda: bool(heartbeat))
            self.assertFalse(self.app._closed)
            release.set()
            self._pump_until(lambda: self.app._closed)

    def test_cancel_retry_analysis_records_all_requested_jpgs(self):
        paths = sorted(self.jpg.glob("*.jpg"))
        plan = SimpleNamespace(
            paths=paths, context=lambda: {"retry_of": "previous"},
            report=SimpleNamespace(source=str(self.jpg), destination=str(self.work),
                                   folders={"raw_source": str(self.raw)}, context={"recursive": True}),
        )
        entered = threading.Event()

        def analyze(*args, cancel_event, **kwargs):
            self.assertEqual(kwargs["jpg_files"], paths)
            entered.set()
            if cancel_event.wait(3):
                raise selector.AnalysisCancelled()
            raise AssertionError("Test retry was not cancelled")

        with patch.object(self.app.service, "analyze", side_effect=analyze), \
                patch("ndex_common.workflow.record_extract") as record:
            self.app._retry_extract(plan)
            self._pump_until(entered.is_set)
            self.app.cancel_work()
            self._pump_until(lambda: not self.app._busy)
        result = record.call_args.args[3]
        self.assertEqual((result.total, result.errors, result.cancelled), (3, 3, True))
        self.assertEqual([item["path"] for item in result.items], [str(path) for path in paths])
        self.assertEqual(list(self.work.iterdir()), [])

    def test_failed_report_cancels_pending_close_and_keeps_results_visible(self):
        self._ready_for_copy()
        entered, release = threading.Event(), threading.Event()

        def record(*args, **kwargs):
            entered.set()
            release.wait(3)
            return None

        with patch.object(self.app, "_save_settings"), \
                patch("ndex_common.workflow.record_extract", side_effect=record), \
                patch("ndex_auto_selector.ndex_auto_selector.ui.tk_app.messagebox.showwarning") as warning:
            self.app.start_copy()
            self._pump_until(entered.is_set)
            self.app._on_close()
            release.set()
            self._pump_until(lambda: not self.app._busy)
        self.assertFalse(self.app._closed)
        self.assertFalse(self.app._closing)
        warning.assert_called_once()
        self.assertEqual(len(list(self.work.glob("*.CR3"))), 3)
        self.assertIn("Couldn't save the job record", self.app.status_var.get())
        self.assertTrue(all(str(widget.cget("state")) == state
                            for widget, state in self.app._input_widgets))

    def test_worker_error_cancels_pending_close_and_restores_inputs(self):
        self._ready_for_copy()
        entered, release = threading.Event(), threading.Event()

        def copy(*args, **kwargs):
            entered.set()
            release.wait(3)
            raise OSError("destination unavailable")

        with patch.object(self.app, "_save_settings"), \
                patch.object(self.app.service, "copy_matches", side_effect=copy), \
                patch("ndex_auto_selector.ndex_auto_selector.ui.tk_app.messagebox.showerror") as error:
            self.app.start_copy()
            self._pump_until(entered.is_set)
            self.app._on_close()
            release.set()
            self._pump_until(lambda: not self.app._busy)
        self.assertFalse(self.app._closed)
        self.assertFalse(self.app._closing)
        error.assert_called_once_with("Error", "destination unavailable")
        self.assertTrue(all(str(widget.cget("state")) == state
                            for widget, state in self.app._input_widgets))


if __name__ == "__main__":
    unittest.main()
