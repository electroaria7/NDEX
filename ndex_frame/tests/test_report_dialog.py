from __future__ import annotations

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from ndex_common.report import JobItem, JobReport
from ndex_common.retry import plan_retry
from ndex_frame.core.models import (
    AspectRatio,
    FramePreset,
    MetadataPolicy,
    OutputProfile,
    OutputSizing,
    SourceItem,
)
from ndex_frame.ui.main_window import MainWindow
from ndex_frame.ui.report_dialog import FrameJobReportDialog, item_listing
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState


def _report(**overrides) -> JobReport:
    fields = {
        "manifest_path": Path("export-20260902T101500Z.json"),
        "type": "export",
        "app": "frame",
        "created_at": "2026-09-02T10:15:00Z",
        "source": "",
        "destination": "",
        "counts": {"copied": 5, "failed": 1},
        "items": (
            JobItem(path="good.jpg", status="exported"),
            JobItem(path="bad.jpg", status="failed", detail="unreadable"),
        ),
        "context": {},
    }
    fields.update(overrides)
    return JobReport(**fields)


def _source(path: Path) -> SourceItem:
    return SourceItem(path=path, oriented_width=4000, oriented_height=3000, has_icc=False)


class FrameJobReportDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        frame = FramePreset("frame", "White 3:4", 1, AspectRatio(3, 4), "#FFFFFF", 1.0, 0.0, 0.0)
        output = OutputProfile(
            "output", "Instagram Feed HQ", 1, OutputSizing("fixed_width", width=1080),
            "jpeg", 95, "4:4:4", "sRGB", True, MetadataPolicy()
        )
        self.state = WorkspaceState(working_frame=frame, output_profile=output)
        self.controller = WorkspaceController(
            self.state, settings_writer=lambda _section, _values: None
        )

    def test_dialog_shows_the_first_report_and_its_items(self) -> None:
        dialog = FrameJobReportDialog([_report()])
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.job_list.count(), 1)
        self.assertIn("5 copied, 1 failed", dialog.summary_label.text())
        self.assertIn("bad.jpg", dialog.item_view.toPlainText())
        self.assertIn("unreadable", dialog.item_view.toPlainText())

    def test_copy_button_is_disabled_without_problems(self) -> None:
        clean = _report(counts={"copied": 5}, items=(JobItem(path="good.jpg", status="exported"),))
        dialog = FrameJobReportDialog([clean])
        self.addCleanup(dialog.close)
        self.assertFalse(dialog.copy_button.isEnabled())

    def test_copy_button_puts_problem_paths_on_the_clipboard(self) -> None:
        dialog = FrameJobReportDialog([_report()])
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.copy_button.isEnabled())
        dialog.copy_button.click()
        clipboard = QApplication.clipboard()
        assert clipboard is not None
        self.assertEqual(clipboard.text(), "bad.jpg")

    def test_output_button_needs_a_folder_that_exists(self) -> None:
        dialog = FrameJobReportDialog([_report(destination="Z:/gone")])
        self.addCleanup(dialog.close)
        self.assertFalse(dialog.output_button.isEnabled())

    def test_selecting_another_job_updates_the_detail(self) -> None:
        older = _report(created_at="2026-09-01T09:00:00Z", counts={"copied": 2}, items=())
        dialog = FrameJobReportDialog([_report(), older])
        self.addCleanup(dialog.close)
        dialog.job_list.setCurrentRow(1)
        self.assertIn("2 copied", dialog.summary_label.text())
        self.assertIn("no per-file items", dialog.item_view.toPlainText())

    def test_item_listing_puts_problems_first(self) -> None:
        listing = item_listing(_report())
        self.assertLess(listing.index("failed"), listing.index("exported"))


class MainWindowJobResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        frame = FramePreset("frame", "White 3:4", 1, AspectRatio(3, 4), "#FFFFFF", 1.0, 0.0, 0.0)
        output = OutputProfile(
            "output", "Instagram Feed HQ", 1, OutputSizing("fixed_width", width=1080),
            "jpeg", 95, "4:4:4", "sRGB", True, MetadataPolicy()
        )
        self.state = WorkspaceState(working_frame=frame, output_profile=output)
        self.controller = WorkspaceController(
            self.state, settings_writer=lambda _section, _values: None
        )

    def test_job_results_opens_a_dialog_when_exports_exist(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.set_interactive_dialogs(False)
        with patch("ndex_frame.ui.report_dialog.frame_reports", return_value=[_report()]):
            dialog = window._open_job_results()
        self.assertIsNotNone(dialog)
        assert dialog is not None
        self.addCleanup(dialog.close)

    def test_job_results_says_so_when_nothing_is_recorded(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.set_interactive_dialogs(False)
        with patch("ndex_frame.ui.report_dialog.frame_reports", return_value=[]):
            dialog = window._open_job_results()
        self.assertIsNone(dialog)
        self.assertIn("No export results", window.statusBar().currentMessage())

class FrameRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        frame = FramePreset("frame", "White 3:4", 1, AspectRatio(3, 4), "#FFFFFF", 1.0, 0.0, 0.0)
        output = OutputProfile(
            "output", "Instagram Feed HQ", 1, OutputSizing("fixed_width", width=1080),
            "jpeg", 95, "4:4:4", "sRGB", True, MetadataPolicy()
        )
        self.state = WorkspaceState(working_frame=frame, output_profile=output)
        self.controller = WorkspaceController(
            self.state, settings_writer=lambda _section, _values: None
        )
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.failed = self.root / "bad.jpg"
        self.failed.write_bytes(b"jpg")

    def _failed_report(self, **overrides) -> JobReport:
        fields = {
            "destination": str(self.root),
            "items": (JobItem(path=str(self.failed), status="failed", detail="unreadable"),),
        }
        fields.update(overrides)
        return _report(**fields)

    def _window(self) -> MainWindow:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.set_interactive_dialogs(False)
        return window

    def test_dialog_enables_retry_for_a_file_that_is_still_there(self) -> None:
        dialog = FrameJobReportDialog([self._failed_report()], retry=lambda _plan: None)
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.retry_button.isEnabled())

    def test_dialog_has_no_retry_button_without_a_handler(self) -> None:
        dialog = FrameJobReportDialog([self._failed_report()])
        self.addCleanup(dialog.close)
        # Never added to a layout, so it has no parent to be drawn in.
        self.assertIsNone(dialog.retry_button.parent())

    def test_dialog_hands_the_plan_over(self) -> None:
        handed = []
        dialog = FrameJobReportDialog([self._failed_report()], retry=handed.append)
        dialog.retry_button.click()
        self.assertEqual(len(handed), 1)
        self.assertEqual(handed[0].paths, (self.failed,))

    def test_retry_refuses_when_the_output_folder_is_gone(self) -> None:
        window = self._window()
        window.confirm_export = Mock()
        window._retry_export(plan_retry(self._failed_report(destination="Z:/gone")))
        window.confirm_export.assert_not_called()
        self.assertIsNone(window.pending_retry)
        self.assertIn("output folder is gone", window.statusBar().currentMessage())

    def test_retry_exports_the_failed_file_without_reimporting_when_it_is_open(self) -> None:
        window = self._window()
        window.confirm_export = Mock()
        self.controller.import_paths = Mock()
        self.state.replace_sources([_source(self.failed)])

        window._retry_export(plan_retry(self._failed_report()))

        self.controller.import_paths.assert_not_called()
        window.confirm_export.assert_called_once()
        exported = [source.path for source in window.confirm_export.call_args.args[0]]
        self.assertEqual(exported, [self.failed])
        self.assertEqual(self.state.output_directory, self.root)
        self.assertIsNotNone(window.pending_retry)

    def test_retry_loads_the_failed_file_when_it_is_not_open(self) -> None:
        window = self._window()
        window.confirm_export = Mock()
        self.controller.import_paths = Mock()

        window._retry_export(plan_retry(self._failed_report()))

        self.controller.import_paths.assert_called_once_with([self.failed])
        window.confirm_export.assert_not_called()

    def test_the_queued_export_starts_once_the_import_lands(self) -> None:
        window = self._window()
        window.confirm_export = Mock()
        window.pending_retry = plan_retry(self._failed_report())
        window._retry_paths = [self.failed]
        self.state.replace_sources([_source(self.failed)])

        window._sources_changed()
        window._start_pending_retry()

        self.assertIsNone(window._retry_paths)
        window.confirm_export.assert_called_once()

    def test_an_unrelated_import_drops_the_retry_instead_of_exporting(self) -> None:
        window = self._window()
        window.confirm_export = Mock()
        window.pending_retry = plan_retry(self._failed_report())
        window._retry_paths = [self.failed]
        other = self.root / "other.jpg"
        other.write_bytes(b"jpg")
        self.state.replace_sources([_source(other)])

        window._sources_changed()
        window._start_pending_retry()

        window.confirm_export.assert_not_called()
        self.assertIsNone(window.pending_retry)
        self.assertIn("different files", window.statusBar().currentMessage())

    def test_a_failed_import_drops_the_retry(self) -> None:
        window = self._window()
        window.pending_retry = plan_retry(self._failed_report())
        window._retry_paths = [self.failed]

        # What the controller emits when an import job raises.
        window._busy_changed(False)

        self.assertIsNone(window._retry_paths)
        self.assertIsNone(window.pending_retry)
        self.assertIn("could not be opened", window.statusBar().currentMessage())

    def test_retry_waits_for_a_running_job(self) -> None:
        window = self._window()
        window.confirm_export = Mock()
        window._busy = True

        window._retry_export(plan_retry(self._failed_report()))

        window.confirm_export.assert_not_called()
        self.assertIsNone(window.pending_retry)
        self.assertIn("running job", window.statusBar().currentMessage())

    def test_a_plan_with_nothing_left_on_disk_is_explained(self) -> None:
        window = self._window()
        window.confirm_export = Mock()
        gone = self._failed_report(items=(JobItem(path="Z:/gone/bad.jpg", status="failed"),))

        window._retry_export(plan_retry(gone))

        window.confirm_export.assert_not_called()
        self.assertIn("nothing to retry", window.statusBar().currentMessage())

    def test_an_export_that_cannot_start_drops_the_retry(self) -> None:
        window = self._window()
        window.confirm_export = Mock(side_effect=RuntimeError("An export job is already running."))
        self.state.replace_sources([_source(self.failed)])

        window._retry_export(plan_retry(self._failed_report()))

        self.assertIsNone(window.pending_retry)
        self.assertIn("Retry stopped", window.statusBar().currentMessage())


class SelectOnOpenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_the_named_job_is_selected(self) -> None:
        newer = _report(manifest_path=Path("C:/m/export-2.json"), created_at="2026-09-02T12:00:00Z")
        older = _report(manifest_path=Path("C:/m/export-1.json"))
        dialog = FrameJobReportDialog([newer, older], select=Path("c:/M/export-1.json"))
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.job_list.currentRow(), 1)
        self.assertIs(dialog.current, older)

    def test_frame_reports_reads_in_a_job_that_aged_out(self) -> None:
        from ndex_frame.ui import report_dialog

        aged = _report(manifest_path=Path("C:/m/export-0.json"), created_at="2026-08-01T00:00:00Z")
        with (
            patch.object(report_dialog, "recent_reports", return_value=[_report()]),
            patch.object(report_dialog, "read_report", return_value=aged),
        ):
            reports = report_dialog.frame_reports(select=Path("C:/m/export-0.json"))
        self.assertIs(reports[0], aged)

    def test_queue_job_results_opens_the_dialog_at_that_job(self) -> None:
        frame = FramePreset("frame", "White 3:4", 1, AspectRatio(3, 4), "#FFFFFF", 1.0, 0.0, 0.0)
        output = OutputProfile(
            "output", "Instagram Feed HQ", 1, OutputSizing("fixed_width", width=1080),
            "jpeg", 95, "4:4:4", "sRGB", True, MetadataPolicy()
        )
        controller = WorkspaceController(
            WorkspaceState(working_frame=frame, output_profile=output),
            settings_writer=lambda _section, _values: None,
        )
        window = MainWindow(controller=controller)
        self.addCleanup(window.close)
        window.set_interactive_dialogs(False)
        wanted = _report(manifest_path=Path("C:/m/export-1.json"))
        with patch("ndex_frame.ui.report_dialog.frame_reports", return_value=[_report(), wanted]) as reports:
            window.queue_job_results(Path("C:/m/export-1.json"))
        reports.assert_called_once_with(select=Path("C:/m/export-1.json"))
        dialog = window._last_report_dialog
        assert dialog is not None
        self.addCleanup(dialog.close)
        self.assertIs(dialog.current, wanted)



if __name__ == "__main__":
    unittest.main()
