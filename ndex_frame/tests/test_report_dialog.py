from __future__ import annotations

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from ndex_common.report import JobItem, JobReport
from ndex_frame.core.models import AspectRatio, FramePreset, MetadataPolicy, OutputProfile, OutputSizing
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


if __name__ == "__main__":
    unittest.main()
