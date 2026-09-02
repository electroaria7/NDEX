from __future__ import annotations

import gc
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common import report_dialog
from ndex_common.report import JobItem, JobReport


def _report(**overrides) -> JobReport:
    fields = {
        "manifest_path": Path("backup-20260902T101500Z.json"),
        "type": "backup",
        "app": "ndex_one",
        "created_at": "2026-09-02T10:15:00Z",
        "source": "",
        "destination": "",
        "counts": {"copied": 42, "failed": 1},
        "items": (
            JobItem(path="a.CR3", status="copied"),
            JobItem(path="b.CR3", status="failed", detail="disk full"),
        ),
        "context": {},
    }
    fields.update(overrides)
    return JobReport(**fields)


class JobReportWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._close_root)

    def _close_root(self) -> None:
        # Release the interpreter on this thread. Left to the garbage
        # collector it can be finalized from a worker thread in a later
        # test, and Tcl aborts the process.
        self.root.destroy()
        del self.root
        gc.collect()

    def _open(self, reports) -> report_dialog.JobReportWindow:
        window = report_dialog.JobReportWindow(self.root, title="NDEX One", reports=reports)
        self.addCleanup(window.destroy)
        return window

    def test_first_job_is_selected_and_rendered(self) -> None:
        window = self._open([_report()])
        self.assertEqual(window.detail_title.cget("text"), "NDEX One - Backup")
        self.assertIn("42 copied, 1 failed", window.detail_counts.cget("text"))
        listing = window.item_text.get("1.0", tk.END)
        self.assertIn("b.CR3", listing)
        self.assertIn("disk full", listing)

    def test_problem_statuses_are_listed_before_successes(self) -> None:
        window = self._open([_report()])
        listing = window.item_text.get("1.0", tk.END)
        self.assertLess(listing.index("failed"), listing.index("copied"))

    def test_jobs_with_problems_are_flagged_in_the_list(self) -> None:
        clean = _report(counts={"copied": 3}, items=(JobItem(path="a.CR3", status="copied"),))
        window = self._open([_report(), clean])
        self.assertEqual(window.job_list.item("0", "tags"), ("problem",))
        self.assertEqual(window.job_list.item("1", "tags"), "")

    def test_copy_button_is_disabled_when_nothing_failed(self) -> None:
        clean = _report(counts={"copied": 3}, items=(JobItem(path="a.CR3", status="copied"),))
        window = self._open([clean])
        self.assertIn("disabled", window.copy_button.state())

    def test_copy_button_puts_problem_paths_on_the_clipboard(self) -> None:
        window = self._open([_report()])
        self.assertNotIn("disabled", window.copy_button.state())
        with patch.object(report_dialog.messagebox, "showinfo"):
            window._copy_problems()
        self.assertEqual(window.clipboard_get(), "b.CR3")

    def test_folder_buttons_need_folders_that_exist(self) -> None:
        window = self._open([_report(source="Z:/gone", destination="Z:/also-gone")])
        self.assertIn("disabled", window.source_button.state())
        self.assertIn("disabled", window.destination_button.state())

    def test_selecting_another_job_updates_the_detail(self) -> None:
        older = _report(
            app="frame",
            type="export",
            created_at="2026-09-01T09:00:00Z",
            counts={"copied": 2},
            items=(),
        )
        window = self._open([_report(), older])
        window.job_list.selection_set("1")
        window._show_selected()
        self.assertEqual(window.detail_title.cget("text"), "NDEX Frame - Export")
        self.assertIn("no per-file items", window.item_text.get("1.0", tk.END))

    def test_cancelled_jobs_are_marked(self) -> None:
        window = self._open([_report(context={"cancelled": True})])
        self.assertIn("cancelled", window.detail_counts.cget("text"))


class OpenJobReportsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._close_root)

    def _close_root(self) -> None:
        # Release the interpreter on this thread. Left to the garbage
        # collector it can be finalized from a worker thread in a later
        # test, and Tcl aborts the process.
        self.root.destroy()
        del self.root
        gc.collect()

    def test_explains_itself_when_no_job_has_run(self) -> None:
        with patch.object(report_dialog.messagebox, "showinfo") as info:
            window = report_dialog.open_job_reports(self.root, title="NDEX One", reports=[])
        self.assertIsNone(window)
        info.assert_called_once()
        self.assertIn("No job results yet", info.call_args.args[1])

    def test_reads_the_manifest_folder_when_reports_are_not_given(self) -> None:
        with patch.object(report_dialog, "recent_reports", return_value=[_report()]) as recent:
            window = report_dialog.open_job_reports(
                self.root, title="Image Manager", apps=("image_manager",)
            )
        assert window is not None
        self.addCleanup(window.destroy)
        self.assertEqual(recent.call_args.kwargs["apps"], ("image_manager",))


class RevealFolderTests(unittest.TestCase):
    def test_missing_folder_is_not_opened(self) -> None:
        with patch.object(report_dialog.subprocess, "Popen") as popen:
            self.assertFalse(report_dialog.reveal_folder(Path("Z:/definitely/not/here")))
        popen.assert_not_called()

    def test_existing_folder_is_handed_to_the_file_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(report_dialog.subprocess, "Popen") as popen:
                self.assertTrue(report_dialog.reveal_folder(Path(tmp)))
            popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
