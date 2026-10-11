"""Wording, feedback and keyboard behaviour added by the UX review (batch U5)."""

from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from ndex_frame.core.geometry import build_render_plan
from ndex_frame.core.messages import (
    ImportSummary,
    clean_text,
    describe_error,
    import_status_text,
    unreadable_message,
)
from ndex_frame.core.models import SourceItem
from ndex_frame.services.export_job import (
    ExportItemResult,
    ExportRequest,
    ExportResult,
    plan_export,
)
from ndex_frame.services.importer import analyze_source, scan_paths
from ndex_frame.services.presets import PresetStore
from ndex_frame.ui.main_window import MainWindow
from ndex_frame.ui.preset_dialog import (
    ExportCompletionDialog,
    colour_notes,
    completion_title,
    describe_preflight,
    failure_lines,
    metadata_summary,
)
from ndex_frame.ui.preview_widget import PreviewWidget, caption_text
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState

NO_PROFILE = "No colour profile — treated as sRGB"


class MessageTests(unittest.TestCase):
    def test_permission_error_names_the_folder_without_doubled_backslashes(self) -> None:
        error = PermissionError(13, "Permission denied", "D:\\Framed\\a.jpg")
        text = describe_error(error, name="a.jpg", folder="D:\\Framed")
        self.assertEqual(
            text, "Can't write to D:\\Framed. Pick another folder or check that it isn't read-only."
        )
        self.assertNotIn("\\\\", text)

    def test_truncated_image_asks_for_a_fresh_copy(self) -> None:
        text = describe_error(OSError("image file is truncated (12 bytes not processed)"), name="IMG_1.jpg")
        self.assertEqual(text, "IMG_1.jpg looks incomplete — copy it from the card again.")

    def test_missing_output_folder_and_missing_source_are_told_apart(self) -> None:
        folder = describe_error(FileNotFoundError(2, "No such file", "D:\\Gone\\x.tmp"), name="a.jpg", folder="D:\\Gone")
        self.assertIn("output folder D:\\Gone was not found", folder)
        source = describe_error(FileNotFoundError(2, "No such file", "C:\\in\\a.jpg"), name="a.jpg", folder="D:\\Out")
        self.assertIn("a.jpg can't be found", source)

    def test_unknown_errors_keep_their_text_but_lose_doubled_backslashes(self) -> None:
        self.assertEqual(clean_text("[Errno 5] bad C:\\\\x\\\\y"), "bad C:\\x\\y")
        self.assertEqual(describe_error(ValueError("odd"), name="a.jpg"), "a.jpg: odd")

    def test_import_status_lines(self) -> None:
        summary = ImportSummary(opened=3, raw_skipped=2)
        self.assertEqual(
            import_status_text(summary, "Image Manager"),
            "Opened 3 of 5 from Image Manager · 2 RAW files skipped "
            "(Frame needs JPG/PNG/TIFF — export them from your RAW editor first)",
        )
        self.assertEqual(import_status_text(ImportSummary(opened=1)), "Opened 1 photo")
        bad = ImportSummary(opened=2, unreadable=(("BAD_0001.jpg", "cannot identify"),))
        self.assertEqual(
            import_status_text(bad), f"Opened 2 of 3 · {unreadable_message('BAD_0001.jpg')}"
        )
        self.assertEqual(
            unreadable_message("BAD_0001.jpg"),
            "BAD_0001.jpg isn't a readable image — re-export it from your editor.",
        )
        self.assertIn("No JPG, PNG or TIFF", import_status_text(ImportSummary()))


class ImporterScanTests(unittest.TestCase):
    def test_scan_reports_raw_and_directly_selected_unsupported_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (8, 8)).save(root / "a.jpg")
            (root / "b.CR3").write_bytes(b"raw")
            (root / "c.xmp").write_bytes(b"sidecar")
            folder = scan_paths([root])
            self.assertEqual([path.name for path in folder.files], ["a.jpg"])
            self.assertEqual([path.name for path in folder.raw_skipped], ["b.CR3"])
            self.assertEqual(folder.unsupported, [])
            direct = scan_paths([root / "c.xmp", root / "b.CR3"])
            self.assertEqual([path.name for path in direct.unsupported], ["c.xmp"])

    def test_missing_profile_warning_is_english(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.png"
            Image.new("RGB", (8, 8)).save(path)
            self.assertEqual(analyze_source(path).warnings, (NO_PROFILE,))


class WindowFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        settings: dict[str, dict[str, str]] = {}
        self.store = PresetStore(
            self.root / "presets",
            lambda section, defaults: {**defaults, **settings.get(section, {})},
            lambda section, values: settings.setdefault(section, {}).update(values),
        )
        self.state = WorkspaceState(
            working_frame=self.store.default_frame(), output_profile=self.store.default_output()
        )
        self.controller = WorkspaceController(self.state, settings_writer=lambda _s, _v: None)
        self.window = MainWindow(self.controller, preset_store=self.store)
        self.window.set_interactive_dialogs(False)
        self.addCleanup(self.window.close)

    def _sources(self, count: int, warnings: tuple[str, ...] = ()) -> list[SourceItem]:
        return [
            SourceItem(self.root / f"IMG_{1000 + i}.JPG", 60, 80, not warnings, warnings)
            for i in range(count)
        ]

    def _output_dir(self) -> Path:
        out = self.root / "out"
        out.mkdir(exist_ok=True)
        return out

    def test_output_folder_label_states(self) -> None:
        window = self.window
        self.assertEqual(
            window.output_folder_label.text(),
            "Output folder: Not selected — choose where framed photos go",
        )
        out = self._output_dir()
        self.state.output_directory = out
        window.sync_output_folder_label()
        self.assertEqual(window.output_folder_label.text(), f"Output folder: {out}")
        self.assertEqual(window.output_folder_label.styleSheet(), "")
        self.state.output_directory = self.root / "vanished"
        window.sync_output_folder_label()
        self.assertTrue(window.output_folder_label.text().endswith("(folder not found)"))
        self.assertIn("color", window.output_folder_label.styleSheet())

    def test_disabled_export_buttons_explain_why(self) -> None:
        window = self.window
        self.assertEqual(window.export_all_button.toolTip(), "Open photos first")
        self.state.replace_sources(self._sources(2))
        window.refresh_thumbnails()
        self.assertEqual(window.export_all_button.toolTip(), "Choose an output folder first")
        self.assertEqual(window.export_selected_button.toolTip(), "Choose an output folder first")
        self.state.output_directory = self._output_dir()
        window.sync_output_folder_label()
        self.assertIn("Ctrl+E", window.export_all_button.toolTip())
        self.assertIn("Ctrl+Shift+E", window.export_selected_button.toolTip())

    def test_warning_badge_and_tooltip_in_image_list(self) -> None:
        self.state.replace_sources(self._sources(1, (NO_PROFILE,)) + self._sources(2)[1:])
        self.window.refresh_thumbnails()
        flagged = self.window.thumbnail_view.item(0)
        clean = self.window.thumbnail_view.item(1)
        self.assertIn("⚠", flagged.text())
        self.assertIn(NO_PROFILE, flagged.toolTip())
        self.assertNotIn("⚠", clean.text())

    def test_colour_notes_summarise_missing_profiles(self) -> None:
        self.assertEqual(colour_notes(self._sources(2)), ())
        self.assertEqual(
            colour_notes(self._sources(3, (NO_PROFILE,))),
            ("3 photos have no colour profile (treated as sRGB)",),
        )
        self.assertEqual(
            colour_notes(self._sources(1, (NO_PROFILE,))),
            ("1 photo has no colour profile (treated as sRGB)",),
        )

    def test_preflight_describes_job_and_real_rename_scheme(self) -> None:
        out = self._output_dir()
        (out / "IMG_1000.jpg").write_bytes(b"x")
        sources = self._sources(2)
        request = ExportRequest(
            tuple(sources), out, self.state.working_frame, self.state.output_profile, (), "skip"
        )
        snapshot = plan_export(request)
        renamed = plan_export(replace(request, collision_policy="rename"))
        info = describe_preflight(snapshot, rename_snapshot=renamed, notes=("n",))
        self.assertEqual(info.total, 2)
        self.assertEqual(info.size_text, "1080 × 1440 px")
        self.assertTrue(info.format_text.startswith("JPEG · quality"))
        self.assertEqual(info.example, "IMG_1000.JPG → IMG_1000.jpg")
        self.assertEqual(info.rename_example, "IMG_1000_01.jpg")
        self.assertEqual(
            metadata_summary(self.state.output_profile.metadata),
            "Capture info kept · copyright kept · GPS location removed",
        )

    def test_prompt_export_uses_skip_by_default_when_files_exist(self) -> None:
        out = self._output_dir()
        (out / "IMG_1000.jpg").write_bytes(b"x")
        self.state.replace_sources(self._sources(2))
        self.state.output_directory = out
        self.window.refresh_thumbnails()
        with patch.object(self.window, "confirm_export") as confirm:
            self.window._export_all()
        confirm.assert_called_once_with(None, "skip")
        dialog = self.window._last_preflight_dialog
        self.assertEqual(dialog.windowTitle(), "Export 2 photos")
        self.assertEqual(dialog.rename_radio.text(), "Keep both — save as IMG_1000_01.jpg")

    def test_blocking_export_error_uses_a_message_box_with_guidance(self) -> None:
        self.state.replace_sources(self._sources(1))
        self.state.output_directory = self._output_dir()
        self.window.refresh_thumbnails()
        self.window.set_interactive_dialogs(True)
        denied = PermissionError(13, "Permission denied", str(self.root / "out"))
        with patch("ndex_frame.ui.main_window.plan_export", side_effect=denied), \
                patch.object(QMessageBox, "warning") as warning:
            self.window._export_all()
        warning.assert_called_once()
        message = warning.call_args.args[2]
        self.assertTrue(message.startswith("Can't write to "))
        self.assertIn("read-only", message)
        self.assertEqual(self.window.statusBar().currentMessage(), message)

    def test_import_status_line_is_shown_after_an_import(self) -> None:
        self.controller.importStatus.emit("Opened 3 of 5 from Image Manager")
        self.assertEqual(self.window.statusBar().currentMessage(), "Opened 3 of 5 from Image Manager")

    def test_real_import_reports_raw_and_unreadable(self) -> None:
        folder = self.root / "card"
        folder.mkdir()
        Image.new("RGB", (16, 16)).save(folder / "good.jpg")
        (folder / "BAD_0001.jpg").write_bytes(b"not an image")
        (folder / "x.CR3").write_bytes(b"raw")
        self.controller.import_paths([folder], origin="card")
        deadline = 200
        while deadline and not self.state.sources:
            QApplication.processEvents()
            QTest.qWait(25)
            deadline -= 1
        self.controller.thread_pool.waitForDone(5000)
        QApplication.processEvents()
        message = self.window.statusBar().currentMessage()
        self.assertTrue(message.startswith("Opened 1 of 3 from card"), message)
        self.assertIn("1 RAW file skipped", message)
        self.assertIn("BAD_0001.jpg isn't a readable image", message)

    def test_frame_preset_shows_edited_marker(self) -> None:
        window = self.window
        name = window.frame_preset_combo.currentData().name
        self.assertEqual(window.frame_preset_combo.currentText(), name)
        window.background_preset_buttons[3].click()
        self.assertEqual(window.frame_preset_combo.currentText(), name + " (edited)")

    def test_reset_override_enabled_only_with_an_override(self) -> None:
        window = self.window
        self.state.replace_sources(self._sources(1))
        window.refresh_thumbnails()
        self.controller.select(self.state.sources[0].path)
        self.assertFalse(window.reset_override_button.isEnabled())
        window.scale_spin.setValue(90)
        self.assertTrue(window.reset_override_button.isEnabled())
        window.reset_override_button.click()
        self.assertFalse(window.reset_override_button.isEnabled())

    def test_apply_all_asks_for_confirmation(self) -> None:
        window = self.window
        self.state.replace_sources(self._sources(3))
        window.refresh_thumbnails()
        self.controller.select(self.state.sources[0].path)
        window.scale_spin.setValue(90)
        window.set_interactive_dialogs(True)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as ask:
            window.apply_all_button.click()
        self.assertEqual(
            ask.call_args.args[2],
            "Apply this framing to all 3 photos? Individual adjustments will be replaced.",
        )
        self.assertTrue(self.state.overrides)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            window.apply_all_button.click()
        self.assertFalse(self.state.overrides)

    def test_toolbar_labels_and_cancel_wording(self) -> None:
        window = self.window
        labels = [label.text().strip() for label in window.findChildren(QLabel)]
        self.assertIn("Frame", labels)
        self.assertIn("Output", labels)
        self.assertEqual(window.cancel_button.text(), "Stop After This Photo")
        self.assertEqual(window.job_results_button.shortcut().toString(), "Ctrl+J")
        self.assertEqual(window.open_files_button.shortcut().toString(), "Ctrl+O")
        self.assertEqual(window.open_folder_button.shortcut().toString(), "Ctrl+Shift+O")
        self.assertEqual(window.export_all_button.shortcut().toString(), "Ctrl+E")
        self.assertEqual(window.export_selected_button.shortcut().toString(), "Ctrl+Shift+E")

    def test_escape_requests_stop_only_while_exporting(self) -> None:
        window = self.window
        with patch.object(self.controller, "cancel_export") as cancel:
            window._escape_pressed()
            cancel.assert_not_called()
            self.controller._export_thread = object()
            try:
                window._escape_pressed()
            finally:
                self.controller._export_thread = None
            cancel.assert_called_once()
        self.assertEqual(window.cancel_button.text(), "Stopping…")

    def test_arrow_keys_step_through_photos_from_the_preview(self) -> None:
        window = self.window
        self.state.replace_sources(self._sources(3))
        window.refresh_thumbnails()
        self.assertEqual(window.thumbnail_view.currentRow(), 0)
        QTest.keyClick(window.preview_widget, Qt.Key.Key_Down)
        self.assertEqual(self.state.selected_path, self.state.sources[1].path)
        QTest.keyClick(window.preview_widget, Qt.Key.Key_Right)
        self.assertEqual(self.state.selected_path, self.state.sources[2].path)
        QTest.keyClick(window.preview_widget, Qt.Key.Key_Right)
        self.assertEqual(self.state.selected_path, self.state.sources[2].path)
        QTest.keyClick(window.preview_widget, Qt.Key.Key_Up)
        self.assertEqual(self.state.selected_path, self.state.sources[1].path)

    def test_dropping_files_and_folders_routes_to_import(self) -> None:
        folder = self.root / "dropped"
        folder.mkdir()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(folder))])
        self.window.handoff_path = Path("handoff.json")
        event = QDropEvent(
            QPointF(10, 10), Qt.DropAction.CopyAction, mime,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )
        with patch.object(self.controller, "import_paths") as import_paths:
            self.window.dropEvent(event)
        import_paths.assert_called_once_with([folder], origin="dropped")
        self.assertIsNone(self.window.handoff_path)
        self.assertTrue(self.window.acceptDrops())

    def test_progress_text_appears_once_in_the_footer_not_the_status_bar(self) -> None:
        from ndex_frame.services.export_job import ExportProgress

        self.window._export_progress(ExportProgress(6, 8, Path("IMG_1006.JPG"), "started"))
        self.assertEqual(self.window.export_progress_label.text(), "Exporting 6 of 8 — IMG_1006.JPG")
        self.assertEqual(self.window.statusBar().currentMessage(), "")


class CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_titles_reflect_the_outcome(self) -> None:
        self.assertEqual(completion_title(ExportResult(8, 0, 0, False, ()), 0), "Exported 8 photos")
        self.assertEqual(completion_title(ExportResult(1, 0, 0, False, ()), 0), "Exported 1 photo")
        failed = ExportResult(3, 0, 1, False, (
            ExportItemResult(Path("BAD.jpg"), Path("BAD.out"), "failed", "BAD.jpg looks incomplete"),
        ))
        self.assertEqual(completion_title(failed, 0), "Exported 3 of 4 — 1 failed")
        stopped = ExportResult(5, 0, 3, True, tuple(
            ExportItemResult(Path(f"{i}.jpg"), Path(f"{i}.out"), "failed", "not run: cancelled")
            for i in range(3)
        ))
        self.assertEqual(completion_title(stopped, 3), "Export stopped — 5 of 8 exported")

    def test_dialog_lists_failures_and_offers_job_results_only_when_available(self) -> None:
        result = ExportResult(3, 0, 1, False, (
            ExportItemResult(Path("D:/in/BAD_1.jpg"), Path("o"), "failed",
                             "BAD_1.jpg looks incomplete — copy it from the card again."),
        ))
        self.assertEqual(
            failure_lines(result),
            ["BAD_1.jpg looks incomplete — copy it from the card again."],
        )
        calls = []
        dialog = ExportCompletionDialog(result, 0, None, on_view_results=lambda: calls.append(1))
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.windowTitle(), "Exported 3 of 4 — 1 failed")
        self.assertFalse(dialog.failures_text.isHidden())
        self.assertIn("BAD_1.jpg", dialog.failures_text.toPlainText())
        self.assertTrue(dialog.job_results_button.isHidden())
        dialog.set_job_results_available(True)
        self.assertFalse(dialog.job_results_button.isHidden())
        dialog.job_results_button.click()
        self.assertEqual(calls, [1])
        self.assertEqual(dialog.close_button.text(), "Close")

    def test_clean_run_hides_failure_list(self) -> None:
        dialog = ExportCompletionDialog(ExportResult(2, 0, 0, False, ()), 0, None)
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.failures_text.isHidden())
        self.assertEqual(dialog.open_folder_button.text(), "Open Output Folder")


class PreviewCaptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_caption_shows_size_and_ratio(self) -> None:
        plan = build_render_plan((6000, 4000), (1080, 1440), 1.0, 0.0, 0.0)
        self.assertEqual(caption_text(plan), "1080×1440 · 3:4")
        self.assertEqual(caption_text(plan, (4, 5)), "1080×1440 · 4:5")

    def test_hint_shows_until_the_first_drag(self) -> None:
        widget = PreviewWidget()
        self.addCleanup(widget.close)
        self.assertTrue(widget._show_hint)
        widget.resize(300, 400)
        plan = build_render_plan((3000, 4000), (1080, 1440), 0.9, 0.0, 0.0)
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QImage, QPixmap

        widget.set_preview(QPixmap.fromImage(QImage(30, 40, QImage.Format.Format_RGB32)), plan)
        widget._drag_start = QPoint(10, 10)
        widget._finish_drag(QPoint(20, 20))
        self.assertFalse(widget._show_hint)


if __name__ == "__main__":
    unittest.main()
