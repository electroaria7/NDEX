from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtWidgets import QApplication

from ndex_common import manifest
from ndex_common import settings as shared_settings
from ndex_frame.core.models import SourceItem
from ndex_frame.services.cache import PreviewCache
from ndex_frame.services.export_job import ExportItemResult, ExportResult
from ndex_frame.services.presets import PresetStore
from ndex_frame.ui.main_window import MainWindow
from ndex_frame.ui.preset_dialog import ExportCompletionDialog
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState


class AppFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temporary.name)
        self.settings: dict[str, dict[str, str]] = {}
        self.store = PresetStore(self.root / "presets-root", self._read_settings, self._write_settings)
        state = WorkspaceState(
            working_frame=self.store.default_frame(),
            output_profile=self.store.default_output(),
        )
        self.controller = WorkspaceController(
            state, preview_cache=PreviewCache(self.root / "cache"),
            settings_writer=lambda _section, _values: None,
        )
        self.window = MainWindow(self.controller, preset_store=self.store)
        self.window.set_interactive_dialogs(False)
        self.addCleanup(self.window.close)

    def tearDown(self) -> None:
        self.controller.cancel_export()
        thread = self.controller._export_thread
        if thread is not None:
            thread.wait(5000)
        self.window.close()
        self.controller.thread_pool.waitForDone(5000)
        QApplication.processEvents()
        self.temporary.cleanup()

    def _read_settings(self, section: str, defaults: dict[str, str]) -> dict[str, str]:
        values = dict(defaults)
        values.update(self.settings.get(section, {}))
        return values

    def _write_settings(self, section: str, values: dict[str, str]) -> None:
        self.settings.setdefault(section, {}).update(values)

    def _wait_until(self, predicate, *, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return
            time.sleep(0.02)
        self.fail("Timed out waiting for application state.")

    def _wait_idle(self) -> None:
        self.controller.thread_pool.waitForDone(5000)
        QApplication.processEvents()

    def test_import_override_preflight_rename_and_export_all(self) -> None:
        source_dir = self.root / "masters"
        output_dir = self.root / "output"
        source_dir.mkdir()
        output_dir.mkdir()
        Image.new("RGB", (60, 80), (12, 34, 56)).save(source_dir / "one.jpg")
        Image.new("RGB", (60, 80), (78, 90, 12)).save(source_dir / "two.jpg")

        self.controller.import_paths([source_dir])
        self._wait_until(lambda: len(self.controller.state.sources) == 2)
        self._wait_idle()

        second = self.controller.state.sources[1]
        self.controller.select(second.path)
        self.window.scale_spin.setValue(90)
        self.window.y_spin.setValue(0.5)

        self.assertTrue(self.controller.state.is_modified(second.path))
        self.assertFalse(self.controller.state.is_modified(self.controller.state.sources[0].path))
        statuses = [self.window.thumbnail_view.item(index).text() for index in range(self.window.thumbnail_view.count())]
        self.assertTrue(any(text.endswith("Modified") or "\nModified" in text for text in statuses))
        self.assertEqual(sum("Modified" in text for text in statuses), 1)

        self.controller.state.output_directory = output_dir
        self.window.sync_output_folder_label()
        counts = self.window.preflight()
        self.assertEqual(counts.exportable, 2)
        self.assertEqual(counts.conflicted, 0)
        self.assertEqual(counts.invalid, 0)

        self.window.confirm_export(collision_policy="rename")
        self._wait_until(lambda: self.window.last_export_result is not None)

        outputs = sorted(output_dir.glob("*.jpg"))
        self.assertEqual([path.name for path in outputs], ["one.jpg", "two.jpg"])
        for path in outputs:
            with Image.open(path) as image:
                self.assertEqual(image.size, (1080, 1440))

        self.assertTrue(self.controller.state.is_modified(second.path))
        statuses = [self.window.thumbnail_view.item(index).text() for index in range(self.window.thumbnail_view.count())]
        self.assertEqual(sum("Exported" in text for text in statuses), 2)
        self.assertFalse(any("Modified" in text for text in statuses))

    def test_preflight_reports_existing_files_as_conflicted_without_overwrite(self) -> None:
        source_dir = self.root / "conflict-masters"
        output_dir = self.root / "conflict-output"
        source_dir.mkdir()
        output_dir.mkdir()
        Image.new("RGB", (60, 80), (9, 8, 7)).save(source_dir / "shot.jpg")
        existing = output_dir / "shot.jpg"
        existing.write_bytes(b"keep-me")

        self.controller.import_paths([source_dir])
        self._wait_until(lambda: len(self.controller.state.sources) == 1)
        self._wait_idle()
        self.controller.state.output_directory = output_dir
        counts = self.window.preflight()

        self.assertEqual(counts.exportable, 0)
        self.assertEqual(counts.conflicted, 1)
        self.assertEqual(counts.invalid, 0)
        self.assertEqual(existing.read_bytes(), b"keep-me")

    def test_preset_combos_load_store_defaults(self) -> None:
        self.assertEqual(self.window.frame_preset_combo.currentText(), "White 3:4")
        self.assertEqual(self.window.output_profile_combo.currentText(), "Instagram Feed HQ")

    def test_export_stays_disabled_without_output_folder(self) -> None:
        self.controller.state.replace_sources(
            [SourceItem(self.root / "one.jpg", 60, 80, True)]
        )
        self.window.refresh_thumbnails()
        self.assertFalse(self.window.export_all_button.isEnabled())
        self.assertFalse(self.window.export_selected_button.isEnabled())

    def test_exported_status_wins_over_modified_after_successful_export(self) -> None:
        source = SourceItem(self.root / "tweaked.jpg", 60, 80, True)
        self.controller.state.replace_sources([source])
        self.controller.select(source.path)
        self.window.scale_spin.setValue(90)
        self.assertTrue(self.controller.state.is_modified(source.path))
        self.assertIn("Modified", self.window.thumbnail_view.item(0).text())
        self.window._export_finished(
            ExportResult(
                1,
                0,
                0,
                False,
                (ExportItemResult(source.path, source.path, "exported"),),
            )
        )
        text = self.window.thumbnail_view.item(0).text()
        self.assertTrue(text.endswith("Exported") or "\nExported" in text)
        self.assertNotIn("Modified", text)
        self.assertTrue(self.controller.state.is_modified(source.path))

    def test_thumbnails_show_exported_and_error_status(self) -> None:
        first = SourceItem(self.root / "one.jpg", 60, 80, True)
        second = SourceItem(self.root / "two.jpg", 60, 80, True)
        self.controller.state.replace_sources([first, second])
        self.window.refresh_thumbnails()
        self.window._export_finished(
            ExportResult(
                1,
                0,
                1,
                False,
                (
                    ExportItemResult(first.path, first.path, "exported"),
                    ExportItemResult(second.path, second.path, "failed", "encode failed"),
                ),
            )
        )
        texts = [self.window.thumbnail_view.item(index).text() for index in range(self.window.thumbnail_view.count())]
        self.assertTrue(any(text.endswith("Exported") or "\nExported" in text for text in texts))
        self.assertTrue(any(text.endswith("Error") or "\nError" in text for text in texts))

    def test_cancel_button_shows_cancelling_ellipsis(self) -> None:
        self.window.cancel_button.show()
        self.window.request_cancel()
        self.assertEqual(self.window.cancel_button.text(), "Cancelling…")

    def test_queue_handoff_imports_manifest_files(self) -> None:
        source_dir = self.root / "handoff-masters"
        source_dir.mkdir()
        Image.new("RGB", (32, 32), (10, 20, 30)).save(source_dir / "pick.jpg")
        Image.new("RGB", (32, 32), (40, 50, 60)).save(source_dir / "skip-raw-not-used.jpg")
        handoff = manifest.write_manifest(
            type="select_handoff",
            app="image_manager",
            source=str(source_dir),
            items=[{"path": str(source_dir / "pick.jpg"), "status": "selected"}],
            root=self.root,
        )
        self.window.queue_handoff(handoff)
        self._wait_until(lambda: len(self.controller.state.sources) == 1)
        self._wait_idle()
        self.assertEqual(self.window.handoff_path, handoff)
        self.assertEqual(self.controller.state.sources[0].path.name, "pick.jpg")

    def test_successful_folder_import_writes_frame_last_source(self) -> None:
        source_dir = self.root / "remember-masters"
        source_dir.mkdir()
        Image.new("RGB", (32, 32), (10, 20, 30)).save(source_dir / "shot.jpg")
        local = self.root / "localappdata"
        local.mkdir()
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
            state = WorkspaceState(
                working_frame=self.store.default_frame(),
                output_profile=self.store.default_output(),
            )
            controller = WorkspaceController(
                state, preview_cache=PreviewCache(self.root / "cache-last-source")
            )
            self.addCleanup(lambda: controller.thread_pool.waitForDone(5000))
            controller.import_paths([source_dir])
            self._wait_until(lambda: len(controller.state.sources) == 1)
            controller.thread_pool.waitForDone(5000)
            QApplication.processEvents()
            stored = shared_settings.get_section("frame")
        self.assertEqual(stored.get("last_source"), str(source_dir.resolve()))

    def test_closing_window_cancels_export_and_waits_for_thread(self) -> None:
        source_dir = self.root / "close-masters"
        output_dir = self.root / "close-output"
        source_dir.mkdir()
        output_dir.mkdir()
        Image.new("RGB", (20, 20), (1, 2, 3)).save(source_dir / "one.jpg")
        self.controller.import_paths([source_dir])
        self._wait_until(lambda: len(self.controller.state.sources) == 1)
        self._wait_idle()
        self.controller.state.output_directory = output_dir
        self.window.sync_output_folder_label()

        started = threading.Event()

        def blocking_export(snapshot, progress, cancel):
            started.set()
            while not cancel.is_cancelled():
                time.sleep(0.02)
            return ExportResult(0, 0, 0, True, ())

        with patch("ndex_frame.ui.workspace.run_export", side_effect=blocking_export):
            self.window.confirm_export(collision_policy="rename")
            self._wait_until(started.is_set)
            thread = self.controller._export_thread
            self.assertIsNotNone(thread)
            self.assertTrue(thread.isRunning())
            self.window.close()
            self.assertFalse(thread.isRunning())

    def test_completion_dialog_lists_counts_and_open_folder(self) -> None:
        dialog = ExportCompletionDialog(ExportResult(2, 1, 3, True, ()), 4, self.root / "output")
        self.addCleanup(dialog.close)
        self.assertEqual(
            dialog.summary_label.text(),
            "Exported 2 · Skipped 1 · Failed 3 · Cancelled 4",
        )
        self.assertEqual(dialog.open_folder_button.text(), "Open Output Folder")


if __name__ == "__main__":
    unittest.main()
