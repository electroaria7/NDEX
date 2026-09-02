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

    def _open(self, reports, retry=None, close=True) -> report_dialog.JobReportWindow:
        window = report_dialog.JobReportWindow(
            self.root, title="NDEX One", reports=reports, retry=retry
        )
        if close:
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

class RetryButtonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._close_root)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.present = Path(self.folder.name) / "a.CR3"
        self.present.write_bytes(b"raw")

    def _close_root(self) -> None:
        # Release the interpreter on this thread. Left to the garbage
        # collector it can be finalized from a worker thread in a later
        # test, and Tcl aborts the process.
        self.root.destroy()
        del self.root
        gc.collect()

    def _open(self, reports, retry=None, close=True):
        window = report_dialog.JobReportWindow(
            self.root, title="NDEX One", reports=reports, retry=retry
        )
        if close:
            self.addCleanup(window.destroy)
        return window

    def _failed_report(self, path=None):
        return _report(items=(JobItem(path=str(path or self.present), status="failed"),))

    def test_no_retry_button_without_a_handler(self) -> None:
        window = self._open([self._failed_report()])
        self.assertEqual(window.retry_button.winfo_manager(), "")

    def test_the_button_is_shown_and_enabled_when_a_file_can_be_retried(self) -> None:
        window = self._open([self._failed_report()], retry=lambda _plan: None)
        self.assertEqual(window.retry_button.winfo_manager(), "pack")
        self.assertNotIn("disabled", window.retry_button.state())

    def test_a_gone_file_is_explained_on_click_rather_than_checked_per_selection(self) -> None:
        # Selecting a job must not stat its files: the manifest can point at
        # a card that has since been unplugged. The check happens on click.
        handed = []
        window = self._open([self._failed_report(path="Z:/gone/a.CR3")], retry=handed.append)
        self.assertNotIn("disabled", window.retry_button.state())

        with (
            patch.object(report_dialog.messagebox, "showinfo") as info,
            patch.object(report_dialog.messagebox, "askyesno") as ask,
        ):
            window._retry_failed()

        self.assertEqual(handed, [])
        ask.assert_not_called()
        info.assert_called_once()
        self.assertIn("nothing to retry", info.call_args.args[1])

    def test_the_button_is_disabled_for_a_job_with_no_problems(self) -> None:
        clean = _report(counts={"copied": 3}, items=(JobItem(path="a.CR3", status="copied"),))
        window = self._open([clean], retry=lambda _plan: None)
        self.assertIn("disabled", window.retry_button.state())

    def test_a_select_handoff_cannot_be_retried(self) -> None:
        handoff = _report(
            app="image_manager",
            type="select_handoff",
            items=(JobItem(path=str(self.present), status="failed"),),
        )
        window = self._open([handoff], retry=lambda _plan: None)
        self.assertIn("disabled", window.retry_button.state())

    def test_confirming_hands_the_plan_over_and_closes_the_window(self) -> None:
        handed = []
        window = self._open([self._failed_report()], retry=handed.append, close=False)
        with patch.object(report_dialog.messagebox, "askyesno", return_value=True):
            window._retry_failed()

        self.assertEqual(len(handed), 1)
        self.assertEqual(handed[0].paths, (self.present,))
        self.assertFalse(window.winfo_exists())

    def test_declining_leaves_the_job_alone(self) -> None:
        handed = []
        window = self._open([self._failed_report()], retry=handed.append)
        with patch.object(report_dialog.messagebox, "askyesno", return_value=False):
            window._retry_failed()

        self.assertEqual(handed, [])
        self.assertTrue(window.winfo_exists())

    def test_open_job_reports_passes_the_handler_through(self) -> None:
        handler = lambda _plan: None
        with patch.object(report_dialog, "recent_reports", return_value=[self._failed_report()]):
            window = report_dialog.open_job_reports(
                self.root, title="NDEX One", apps=("ndex_one",), retry=handler
            )
        assert window is not None
        self.addCleanup(window.destroy)
        self.assertIs(window.retry, handler)


class RetryHintTests(unittest.TestCase):
    """What the copy dialog tells you to do with the paths."""

    def test_the_launcher_is_told_which_app_can_retry(self) -> None:
        hint = report_dialog._where_to_retry(_report(), here=False)
        self.assertIn("Open NDEX One", hint)

    def test_the_owning_app_is_pointed_at_its_own_button(self) -> None:
        hint = report_dialog._where_to_retry(_report(), here=True)
        self.assertIn("Retry Failed", hint)

    def test_a_job_no_app_can_rerun_falls_back_to_running_it_again(self) -> None:
        handoff = _report(app="image_manager", type="select_handoff")
        self.assertIn("Re-run the job", report_dialog._where_to_retry(handoff, here=True))


class LauncherHandoffTests(unittest.TestCase):
    """The Launcher cannot retry; it opens the app that can, at that job."""

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

    def _failed(self, **overrides):
        fields = {"items": (JobItem(path="E:/DCIM/a.CR3", status="failed"),)}
        fields.update(overrides)
        return _report(**fields)

    def test_without_a_retry_handler_the_app_button_takes_its_place(self) -> None:
        window = report_dialog.JobReportWindow(
            self.root, title="Launcher", reports=[self._failed()], open_in_app=lambda _r: None
        )
        self.addCleanup(window.destroy)
        self.assertEqual(window.retry_button.winfo_manager(), "")
        self.assertEqual(window.open_app_button.winfo_manager(), "pack")
        self.assertEqual(window.open_app_button.cget("text"), "Retry in NDEX One...")
        self.assertNotIn("disabled", window.open_app_button.state())

    def test_the_app_button_is_disabled_for_a_job_nothing_can_retry(self) -> None:
        handoff = _report(app="image_manager", type="select_handoff")
        window = report_dialog.JobReportWindow(
            self.root, title="Launcher", reports=[handoff], open_in_app=lambda _r: None
        )
        self.addCleanup(window.destroy)
        self.assertIn("disabled", window.open_app_button.state())

    def test_the_app_button_hands_the_report_over_and_closes(self) -> None:
        handed = []
        report = self._failed()
        window = report_dialog.JobReportWindow(
            self.root, title="Launcher", reports=[report], open_in_app=handed.append
        )
        window._open_in_app()
        self.assertEqual(handed, [report])
        self.assertFalse(window.winfo_exists())

    def test_an_app_with_its_own_retry_does_not_show_the_app_button(self) -> None:
        window = report_dialog.JobReportWindow(
            self.root,
            title="NDEX One",
            reports=[self._failed()],
            retry=lambda _p: None,
            open_in_app=lambda _r: None,
        )
        self.addCleanup(window.destroy)
        self.assertEqual(window.open_app_button.winfo_manager(), "")


class SelectOnOpenTests(unittest.TestCase):
    """--retry lands on the job it names, even one that aged out of the list."""

    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._close_root)

    def _close_root(self) -> None:
        self.root.destroy()
        del self.root
        gc.collect()

    def test_the_named_job_is_selected(self) -> None:
        newer = _report(manifest_path=Path("C:/m/backup-2.json"), created_at="2026-09-02T12:00:00Z")
        older = _report(manifest_path=Path("C:/m/backup-1.json"))
        window = report_dialog.JobReportWindow(
            self.root, title="NDEX One", reports=[newer, older], select=Path("c:/M/backup-1.json")
        )
        self.addCleanup(window.destroy)
        self.assertEqual(window.job_list.selection(), ("1",))
        self.assertIs(window.current, older)

    def test_an_unknown_selection_falls_back_to_the_newest(self) -> None:
        window = report_dialog.JobReportWindow(
            self.root, title="NDEX One", reports=[_report()], select=Path("C:/m/nope.json")
        )
        self.addCleanup(window.destroy)
        self.assertEqual(window.job_list.selection(), ("0",))

    def test_open_job_reports_reads_in_a_job_that_aged_out(self) -> None:
        aged = _report(manifest_path=Path("C:/m/backup-0.json"), created_at="2026-08-01T00:00:00Z")
        with (
            patch.object(report_dialog, "recent_reports", return_value=[_report()]),
            patch.object(report_dialog, "read_report", return_value=aged) as read,
        ):
            window = report_dialog.open_job_reports(
                self.root, title="NDEX One", apps=("ndex_one",), select=Path("C:/m/backup-0.json")
            )
        assert window is not None
        self.addCleanup(window.destroy)
        read.assert_called_once_with(Path("C:/m/backup-0.json"))
        self.assertIs(window.current, aged)



if __name__ == "__main__":
    unittest.main()
