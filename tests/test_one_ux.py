from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import gui
from src.file_types import get_file_type_group, get_file_type_label
from src.gui import (
    DUPLICATE_LABEL_TO_POLICY,
    DUPLICATE_POLICY_HINTS,
    DUPLICATE_POLICY_LABELS,
    VERIFY_LABEL_TO_MODE,
    VERIFY_MODE_HINTS,
    VERIFY_MODE_LABELS,
    DSBApp,
    build_completion_status,
    build_confirmation,
    fallback_note,
    format_day_span,
    format_size,
    format_type_counts,
    free_space_warning,
)
from src.logger import format_display_line
from src.models import BackupResult, ScanItem, ScanSummary
from src.scanner import analyze_source, get_free_space


def make_summary(total_size=1_932_735_283, free_space=None, fallback_count=0, root=r"D:\Photos"):
    root = Path(root)
    items = [
        ScanItem(Path(f"IMG_{i}.JPG"), "jpg", datetime(2026, 9, 5 + i % 3, 10), "exif",
                 root / "2026" / "09" / f"090{5 + i % 3}" / "jpg")
        for i in range(3)
    ]
    return ScanSummary(
        source_dir=Path("E:/DCIM"), backup_root=root, items=items,
        counts={"jpg": 24, "cr3": 12, "cr2": 6},
        date_range=(datetime(2026, 9, 5, 8), datetime(2026, 9, 7, 20)),
        preview_rows=[], folder_tree_lines=[],
        total_size=total_size, free_space=free_space, fallback_count=fallback_count,
    )


class WordingTests(unittest.TestCase):
    def test_labels_map_to_the_saved_config_keys(self):
        self.assertEqual(
            {label: key for key, label in DUPLICATE_POLICY_LABELS.items()}, DUPLICATE_LABEL_TO_POLICY
        )
        self.assertEqual(set(DUPLICATE_POLICY_LABELS), {"rename", "smart", "skip", "overwrite"})
        self.assertEqual(set(VERIFY_MODE_LABELS), {"size", "sha256", "none"})
        self.assertEqual(VERIFY_LABEL_TO_MODE["Quick check (file size)"], "size")
        self.assertEqual(DUPLICATE_LABEL_TO_POLICY["Skip identical files"], "smart")
        self.assertEqual(set(DUPLICATE_POLICY_HINTS), set(DUPLICATE_POLICY_LABELS))
        self.assertEqual(set(VERIFY_MODE_HINTS), set(VERIFY_MODE_LABELS))

    def test_file_type_labels_say_raw(self):
        self.assertEqual(get_file_type_label("jpg"), "JPG")
        self.assertEqual(get_file_type_label("cr3"), "Canon RAW (.CR3)")
        self.assertEqual(get_file_type_group("jpg"), "JPG")
        self.assertEqual(get_file_type_group("cr3"), "RAW")

    def test_counts_are_grouped_as_jpg_and_raw(self):
        self.assertEqual(format_type_counts({"jpg": 24, "cr3": 12, "cr2": 6}), "JPG 24 \u00b7 RAW 18")
        self.assertEqual(format_type_counts({"jpg": 0, "cr3": 0}), "None")

    def test_size_formatting(self):
        self.assertEqual(format_size(512), "512 B")
        self.assertEqual(format_size(2048), "2.0 KB")
        self.assertEqual(format_size(1_932_735_283), "1.8 GB")

    def test_fallback_note(self):
        self.assertEqual(fallback_note(0), "")
        self.assertEqual(fallback_note(3), "3 files had no capture date; their modified date was used.")
        self.assertIn("1 file had no capture date", fallback_note(1))


class ConfirmationTests(unittest.TestCase):
    def test_backup_confirmation_text(self):
        title, body = build_confirmation(
            make_summary(), "Skip identical files", "Quick check (file size)", dry_run=False
        )
        self.assertEqual(title, "Start Backup")
        self.assertEqual(
            body.splitlines(),
            [
                "Copy 3 files (1.8 GB) to D:\\Photos?",
                "JPG 24, RAW 18 \u00b7 3 days (2026-09-05 to 2026-09-07)",
                "If a file already exists: Skip identical files",
                "After copying: Quick check (file size)",
                "Nothing is deleted from the source.",
            ],
        )

    def test_dry_run_confirmation_says_nothing_is_copied(self):
        title, body = build_confirmation(make_summary(), "a", "b", dry_run=True)
        self.assertEqual(title, "Start Dry Run")
        self.assertTrue(body.endswith("Nothing will be copied."))

    def test_low_free_space_is_warned_about(self):
        summary = make_summary(total_size=2 * 1024 ** 3, free_space=1024 ** 3)
        _title, body = build_confirmation(summary, "a", "b", dry_run=False)
        self.assertIn("Not enough free space: 2.0 GB needed, only 1.0 GB free", body)
        self.assertEqual(free_space_warning(10, 10), "")
        self.assertEqual(free_space_warning(10, None), "")

    def test_day_span(self):
        one = (datetime(2026, 9, 5, 1), datetime(2026, 9, 5, 23))
        self.assertEqual(format_day_span(one), "1 day (2026-09-05)")
        self.assertEqual(format_day_span((None, None)), "")


class CompletionStatusTests(unittest.TestCase):
    def test_done(self):
        result = BackupResult(total=42, copied=42, verified=42)
        self.assertEqual(
            build_completion_status(result), "Done: 42 copied and verified, 0 skipped, 0 errors."
        )

    def test_nothing_new(self):
        result = BackupResult(total=42, skipped=42)
        self.assertEqual(
            build_completion_status(result),
            "Nothing new to copy: all 42 files were already in the backup.",
        )

    def test_stopped(self):
        items = [{"detail": "not run: cancelled"}] * 30 + [{"detail": ""}] * 12
        result = BackupResult(total=42, copied=12, cancelled=True, items=items)
        self.assertEqual(
            build_completion_status(result),
            "Stopped: 12 copied; 30 not run (see Job Results to retry).",
        )

    def test_unverified_copy_is_not_called_verified(self):
        result = BackupResult(total=2, copied=2, verified=0)
        self.assertIn("2 copied (not verified)", build_completion_status(result))


class LogLineTests(unittest.TestCase):
    NOW = datetime(2026, 9, 7, 13, 5, 9)

    def line(self, level, message, **kwargs):
        return format_display_line(level, message, now=self.NOW, destination="D:/Photos", **kwargs)

    def test_one_line_per_copied_file(self):
        text = self.line("OK", "copied IMG_1024.JPG -> D:/Photos/2026/09/0907/jpg", verify_mode="size")
        self.assertEqual(text, "13:05:09  OK  IMG_1024.JPG \u2192 2026/09/0907/jpg (verified)")
        self.assertIsNone(self.line("OK", "verified IMG_1024.JPG (size)"))

    def test_unchecked_copy_is_labelled(self):
        text = self.line("OK", "copied A.JPG -> D:/Photos/2026/09/0907/jpg", verify_mode="none")
        self.assertTrue(text.endswith("(not checked)"))

    def test_skips_and_plain_info(self):
        self.assertEqual(self.line("SKIP", "A.JPG already exists"), "13:05:09  SKIP  A.JPG (already exists)")
        self.assertIn("identical", self.line("SKIP", "A.JPG identical file already backed up as A_001.JPG"))
        self.assertEqual(self.line("INFO", "Found 42 supported files"), "13:05:09  Found 42 supported files")


class ScannerSummaryTests(unittest.TestCase):
    class Extractor:
        def get_capture_datetimes(self, files, logger=None):
            return {path: (datetime(2026, 9, 5), "mtime", True) for path in files}

    def test_summary_has_size_free_space_and_fallback_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "a.jpg").write_bytes(b"x" * 100)
            (root / "src" / "b.jpg").write_bytes(b"y" * 50)
            summary = analyze_source(root / "src", root / "backup", self.Extractor(), ["jpg"])
            self.assertEqual(summary.total_size, 150)
            self.assertEqual(summary.fallback_count, 2)
            self.assertGreater(summary.free_space, 0)
            self.assertIsNotNone(get_free_space(root / "does" / "not" / "exist"))


class WindowTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "appdata")})
        env.start()
        self.addCleanup(env.stop)
        self.app = DSBApp(preload_only=True)
        self.app.withdraw()
        self.addCleanup(self._destroy)

    def _destroy(self):
        try:
            for timer in self.app.tk.call("after", "info"):
                self.app.after_cancel(timer)
            self.app.destroy()
        except Exception:
            pass

    def test_preview_button_is_gone_and_empty_state_guides(self):
        self.assertFalse(hasattr(self.app, "preview_button"))
        self.assertIn("3. Press Analyze.", self.app.summary_var.get())

    def test_hints_follow_the_comboboxes(self):
        self.app.duplicate_var.set("Overwrite existing")
        self.app.verify_var.set("No check")
        self.assertEqual(self.app.duplicate_hint_var.get(), DUPLICATE_POLICY_HINTS["overwrite"])
        self.assertEqual(self.app.verify_hint_var.get(), VERIFY_MODE_HINTS["none"])

    def test_accent_and_enter_follow_the_next_step(self):
        app = self.app
        app.source_var.set(str(self.root))
        app.destination_var.set(str(self.root / "out"))
        self.assertEqual(str(app.analyze_button.cget("style")), "Accent.TButton")
        self.assertIs(app._primary_action()[0], app.analyze_button)
        with patch.object(app, "_start_analysis") as analyze:
            self.assertEqual(app._on_enter(), "break")
            analyze.assert_called_once()
        app.current_summary = make_summary()
        app._update_button_states()
        self.assertEqual(str(app.backup_button.cget("style")), "Accent.TButton")
        self.assertEqual(str(app.analyze_button.cget("style")), "TButton")
        with patch.object(app, "_start_backup") as backup:
            app._on_enter()
            backup.assert_called_once()

    def test_enter_does_nothing_while_busy(self):
        self.app.source_var.set(str(self.root))
        self.app.destination_var.set(str(self.root / "out"))
        self.app._set_busy(True, "Working")
        with patch.object(self.app, "_start_analysis") as analyze:
            self.assertIsNone(self.app._on_enter())
            analyze.assert_not_called()

    def test_invalid_source_message(self):
        self.app.source_var.set(str(self.root / "missing"))
        self.app.destination_var.set(str(self.root / "out"))
        with patch.object(gui.messagebox, "showerror") as showerror:
            self.app._start_analysis()
        showerror.assert_called_once_with("Invalid Source", gui.INVALID_SOURCE_MESSAGE)

    def test_cancel_and_completion_status(self):
        self.app._set_busy(True, "Working")
        self.app.is_analyzing = False
        self.app._cancel_task()
        self.assertEqual(self.app.status_var.get(), gui.STOPPING_STATUS)
        self.app._set_busy(False, "Done", progress=100.0)
        self.assertEqual(self.app.progress_var.get(), 100.0)

    def test_clean_run_shows_completion_dialog_and_warnings_offer_job_results(self):
        app = self.app
        clean = BackupResult(total=2, copied=2, verified=2)
        app.ui_queue.put(("backup_done", clean))
        with patch.object(app, "_show_completion_dialog") as dialog:
            self._drain()
        dialog.assert_called_once_with("Done: 2 copied and verified, 0 skipped, 0 errors.")
        self.assertEqual(app.progress_var.get(), 100.0)

        bad = BackupResult(total=2, copied=1, verified=1, errors=1)
        app.ui_queue.put(("backup_done", bad))
        with patch.object(gui.messagebox, "askyesno", return_value=True) as ask, \
                patch.object(app, "_open_job_results") as results:
            self._drain()
        self.assertIn("Open Job Results now?", ask.call_args.args[1])
        results.assert_called_once()

    def test_completion_actions_use_the_finished_jobs_destination(self):
        actual = self.root / "retried-backup"
        actual.mkdir()
        other = self.root / "current-form-folder"
        other.mkdir()
        self.app.destination_var.set(str(other))
        self.app.pending_backup = {"destination": str(actual)}

        def click_action(dialog, label):
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            button = next(w for w in descendants(dialog)
                          if isinstance(w, gui.ttk.Button) and w.cget("text") == label)
            button.invoke()

        for label in ("Open Backup Folder", "Open in Image Manager"):
            with self.subTest(action=label), \
                    patch.object(gui.os, "startfile") as open_folder, \
                    patch.object(gui, "launch_app", return_value=True) as launch, \
                    patch.object(self.app, "wait_window", side_effect=lambda d: click_action(d, label)):
                self.app._show_completion_dialog("Done")
                if label == "Open Backup Folder":
                    self.assertEqual(Path(open_folder.call_args.args[0]), actual)
                else:
                    launch.assert_called_once_with("image_manager", ["--open", "--source", str(actual)])

    def _drain(self):
        app = self.app
        app.after(0, lambda: None)
        for _ in range(5):
            app._process_ui_queue()
            app.update()


if __name__ == "__main__":
    unittest.main()
