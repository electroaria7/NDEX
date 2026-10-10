from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_auto_selector.ndex_auto_selector.core.models import CopyResult
from ndex_auto_selector.ndex_auto_selector.services.selector import AutoSelectorService, shared_camera_id
from ndex_auto_selector.ndex_auto_selector.ui import tk_app
from ndex_auto_selector.ndex_auto_selector.ui.tk_app import (
    AutoSelectorApp,
    banner_for_analysis,
    banner_for_copy,
    candidate_rows,
    handoff_text,
    hint_for_match,
    relative_folder,
)


def _ambiguous_setup(root: Path):
    raw = root / "raw"
    (raw / "card_a").mkdir(parents=True)
    (raw / "card_b").mkdir()
    (raw / "card_a" / "IMG_0001.CR3").write_bytes(b"raw-a")
    (raw / "card_b" / "IMG_0001.CR3").write_bytes(b"raw-b")
    (raw / "IMG_0002.CR3").write_bytes(b"raw-2")
    jpg = root / "jpg"
    jpg.mkdir()
    for name in ("IMG_0001.JPG", "IMG_0002.JPG", "IMG_0003.JPG"):
        (jpg / name).write_bytes(b"jpg")
    return raw, jpg


class AmbiguousChooserServiceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw, self.jpg = _ambiguous_setup(self.root)
        self.work = self.root / "work"
        self.service = AutoSelectorService()

    def test_ambiguous_match_lists_its_candidates(self):
        summary = self.service.analyze(self.raw, self.jpg)
        by_name = {match.jpg_path.name: match for match in summary.matches}
        ambiguous = by_name["IMG_0001.JPG"]
        self.assertEqual(ambiguous.status, "ambiguous")
        self.assertIsNone(ambiguous.raw_path)
        self.assertEqual(
            sorted(path.parent.name for path in ambiguous.candidates), ["card_a", "card_b"])
        self.assertEqual(by_name["IMG_0002.JPG"].candidates, ())
        self.assertEqual(by_name["IMG_0002.JPG"].match_kind, "exact")
        self.assertEqual(by_name["IMG_0003.JPG"].status, "missing")
        self.assertEqual((summary.matched_count, summary.ambiguous_count, summary.missing_count), (1, 1, 1))

    def test_chosen_match_copies_and_is_recorded_as_chosen(self):
        summary = self.service.analyze(self.raw, self.jpg)
        ambiguous = next(m for m in summary.matches if m.status == "ambiguous")
        picked = next(path for path in ambiguous.candidates if path.parent.name == "card_b")
        ambiguous.raw_path, ambiguous.status = picked, "chosen"
        self.assertEqual((summary.chosen_count, summary.copyable_count, summary.ambiguous_count), (1, 2, 0))

        result = self.service.copy_matches(summary.matches, self.work)

        self.assertEqual((result.copied, result.ambiguous, result.missing, result.errors), (2, 0, 1, 0))
        self.assertEqual((self.work / "IMG_0001.CR3").read_bytes(), b"raw-b")
        chosen_items = [item for item in result.items if item.get("detail") == "chosen by user"]
        self.assertEqual(len(chosen_items), 1)
        self.assertEqual(chosen_items[0]["status"], "copied")

    def test_unresolved_ambiguous_match_is_still_skipped(self):
        summary = self.service.analyze(self.raw, self.jpg)
        result = self.service.copy_matches(summary.matches, self.work)
        self.assertEqual((result.copied, result.ambiguous, result.missing), (1, 1, 1))
        self.assertEqual([p.name for p in self.work.iterdir()], ["IMG_0002.CR3"])
        self.assertTrue(any("several RAW files match IMG_0001.JPG" in m for m in result.messages))
        self.assertTrue(any(m == "no RAW found for IMG_0003.JPG" for m in result.messages))

    def test_missing_folder_message_says_raw_folder(self):
        with self.assertRaisesRegex(FileNotFoundError, "RAW folder does not exist"):
            self.service.analyze(self.root / "nope", self.jpg)

    def test_shared_camera_id(self):
        self.assertEqual(shared_camera_id("album_IMG_1004_edit", "IMG_1004"), "IMG_1004")
        self.assertIsNone(shared_camera_id("IMG_1004", "IMG_1004"))


class WordingHelperTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw, self.jpg = _ambiguous_setup(self.root)
        self.summary = AutoSelectorService().analyze(self.raw, self.jpg)
        self.by_name = {m.jpg_path.name: m for m in self.summary.matches}

    def test_banners(self):
        self.assertEqual(
            banner_for_analysis(self.summary), "3 picked \u00b7 1 will copy \u00b7 1 need your choice \u00b7 1 RAW not found")
        result = CopyResult(total=8, copied=4, skipped=1, ambiguous=1, missing=2)
        self.assertEqual(banner_for_copy(result), "Copied 4 \u00b7 Skipped 2 \u00b7 Not found 2 \u00b7 Failed 0")

    def test_hints_follow_the_row(self):
        self.assertEqual(
            hint_for_match(self.by_name["IMG_0003.JPG"], recursive=False),
            "No RAW named IMG_0003 in the RAW folder. Check the folder or turn on Include subfolders.")
        self.assertIn("Include subfolders", hint_for_match(self.by_name["IMG_0003.JPG"], recursive=False))
        self.assertNotIn("Include subfolders", hint_for_match(self.by_name["IMG_0003.JPG"], recursive=True))
        self.assertEqual(
            hint_for_match(self.by_name["IMG_0001.JPG"]),
            "Several RAW files match this photo. Choose one with Choose RAW\u2026")
        exact = hint_for_match(self.by_name["IMG_0002.JPG"])
        self.assertTrue(exact.startswith(str(self.raw / "IMG_0002.CR3")))
        self.assertTrue(exact.endswith("exact name"))
        self.assertEqual(hint_for_match(None), "")

    def test_camera_number_hint(self):
        (self.jpg / "album_IMG_0002_edit.JPG").write_bytes(b"jpg")
        summary = AutoSelectorService().analyze(self.raw, self.jpg)
        match = next(m for m in summary.matches if m.jpg_path.name.startswith("album_"))
        self.assertTrue(hint_for_match(match).endswith("camera number IMG_0002"))

    def test_candidate_rows_and_relative_folder(self):
        rows = candidate_rows(self.by_name["IMG_0001.JPG"], self.raw)
        self.assertEqual({row[0] for row in rows}, {"card_a", "card_b"})
        self.assertEqual({row[1] for row in rows}, {"IMG_0001.CR3"})
        self.assertTrue(all(row[2].endswith(" B") for row in rows))
        self.assertEqual(relative_folder(self.raw / "IMG_0002.CR3", self.raw), "\u2014")
        self.assertEqual(relative_folder(None, self.raw), "")

    def test_handoff_text(self):
        self.assertEqual(handoff_text(8, "D:\\shoot"), "8 photos picked in Image Manager (from D:\\shoot)")
        self.assertEqual(handoff_text(1, "D:\\shoot"), "1 photo picked in Image Manager (from D:\\shoot)")


class SelectorUxAppTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ndex-selector-ux-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw, self.jpg = _ambiguous_setup(self.root)
        self.work = self.root / "work"
        environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "appdata")})
        environment.start()
        self.addCleanup(environment.stop)
        settings = patch.object(tk_app, "get_section", return_value={})
        settings.start()
        self.addCleanup(settings.stop)
        self.app = AutoSelectorApp(self.raw, self.jpg, self.work)
        self.app.withdraw()
        self.addCleanup(self._close)

    def _close(self):
        if not self.app._closed:
            self.app._on_close()
            self._pump(lambda: self.app._closed)

    def _pump(self, condition, timeout=4):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            if not self.app._closed:
                self.app.update()
            time.sleep(0.01)

    def _analyze(self):
        self.app.summary = self.app.service.analyze(self.raw, self.jpg, exclude=self.work)
        self.app._analysis_context = self.app._current_analysis_context()
        self.app._render_summary()
        self.app._render_matches()
        self.app._update_buttons()

    def test_placeholder_then_rows(self):
        self.assertEqual(self.app.placeholder_label.cget("text"), "Choose folders, then press Analyze Matches.")
        self._analyze()
        rows = [self.app.match_tree.item(i, "values") for i in self.app.match_tree.get_children()]
        self.assertEqual(self.app.banner_var.get(),
                         "3 picked \u00b7 1 will copy \u00b7 1 need your choice \u00b7 1 RAW not found")
        self.assertEqual(rows[0][1:], ("(2 candidates)", "", "\u26a0 Multiple RAW found"))
        self.assertEqual(rows[1][3], "\u2714 Matched")
        self.assertEqual(rows[2][3], "\u2716 No RAW found")
        self.assertEqual(self.app.match_tree.cget("columns"), ("jpg", "raw", "location", "status"))

    def test_choose_button_follows_selection_and_choice_updates_row(self):
        self._analyze()
        tree = self.app.match_tree
        tree.selection_set("2")
        self.app.update()
        self.assertEqual(str(self.app.choose_button.cget("state")), "disabled")
        self.assertIn("No RAW named IMG_0003", self.app.hint_var.get())
        tree.selection_set("0")
        self.app.update()
        self.assertEqual(str(self.app.choose_button.cget("state")), "normal")
        candidate = self.app.summary.matches[0].candidates[1]
        with patch.object(self.app, "_run_choose_dialog", return_value=("choose", candidate)):
            self.app.choose_raw()
        match = self.app.summary.matches[0]
        self.assertEqual((match.status, match.raw_path), ("chosen", candidate))
        self.assertEqual(tree.item("0", "values")[1], "IMG_0001.CR3")
        self.assertEqual(tree.item("0", "values")[3], "\u2714 Chosen")
        self.assertIn("2 will copy", self.app.banner_var.get())
        self.assertIn("chosen by you", self.app.hint_var.get())
        with patch.object(self.app, "_run_choose_dialog", return_value=("skip", None)):
            self.app.choose_raw()
        self.assertEqual((match.status, match.raw_path), ("ambiguous", None))
        self.assertIn("1 will copy", self.app.banner_var.get())

    def test_duplicate_labels_map_to_policy(self):
        self.assertEqual(self.app.duplicate_label_var.get(), "Keep both (add _001)")
        self.app.duplicate_label_var.set("Skip existing")
        self.assertEqual(self.app.duplicate_var.get(), "skip")
        self.app.duplicate_label_var.set("Replace existing (cannot be undone)")
        self.assertEqual(self.app._copy_options()["duplicate_policy"], "overwrite")
        self.app.duplicate_var.set("rename")
        self.assertEqual(self.app.duplicate_label_var.get(), "Keep both (add _001)")

    def test_replace_asks_before_copying(self):
        self._analyze()
        self.work.mkdir()
        (self.work / "IMG_0002.CR3").write_bytes(b"old")
        self.app.duplicate_var.set("overwrite")
        with patch.object(tk_app.messagebox, "askyesno", return_value=False) as ask, \
                patch.object(self.app, "_save_settings"):
            self.app.start_copy()
        ask.assert_called_once()
        self.assertIn("Replace up to 1 existing RAW files in the work folder?", ask.call_args.args[1])
        self.assertFalse(self.app._busy)
        self.assertEqual((self.work / "IMG_0002.CR3").read_bytes(), b"old")

    def test_xmp_dependents_follow_the_checkbox(self):
        for widget in self.app._xmp_dependents:
            self.assertEqual(str(widget.cget("state")), "readonly" if "Combobox" in widget.winfo_class() else "normal")
        self.app.write_xmp_var.set(False)
        self.assertTrue(all(str(w.cget("state")) == "disabled" for w in self.app._xmp_dependents))
        self.app.write_xmp_var.set(True)
        self.assertTrue(all(str(w.cget("state")) != "disabled" for w in self.app._xmp_dependents))

    def test_handoff_field_is_read_only_until_the_user_picks_a_folder(self):
        files = sorted(self.jpg.glob("*.JPG"))
        self.app.handoff_files = files
        self.app._handoff_display = str(self.jpg)
        self.app._refresh_handoff_ui()
        self.assertEqual(str(self.app.selected_entry.cget("state")), "readonly")
        self.assertEqual(self.app.selected_display_var.get(), handoff_text(3, str(self.jpg)))
        self.assertTrue(self.app.use_folder_button.winfo_manager())
        self.app._set_busy(True)
        self.app._set_busy(False)
        self.assertEqual(str(self.app.selected_entry.cget("state")), "readonly")

        self.app._leave_handoff()
        self.assertIsNone(self.app.handoff_files)
        self.assertEqual(str(self.app.selected_entry.cget("state")), "normal")
        self.assertEqual(str(self.app.selected_entry.cget("textvariable")), str(self.app.selected_jpg_var))
        self.assertFalse(self.app.use_folder_button.winfo_manager())

    def test_completion_dialog_after_copy(self):
        self._analyze()
        with patch.object(self.app, "_save_settings"), \
                patch.object(tk_app, "CopyDoneDialog") as dialog, \
                patch.object(self.app, "open_job_results") as results:
            self.app.start_copy()
            self._pump(lambda: not self.app._busy)
            dialog.call_args.args[3]()
        dialog.assert_called_once()
        self.assertEqual(self.app.banner_var.get(), "Copied 1 \u00b7 Skipped 1 \u00b7 Not found 1 \u00b7 Failed 0")
        self.assertIn("select", results.call_args.kwargs)
        from ndex_common.report import read_report

        report = read_report(results.call_args.kwargs["select"])
        self.assertIsNotNone(report)
        self.assertEqual(report.destination, str(self.work))
        self.assertEqual(report.counts["copied"], 1)


if __name__ == "__main__":
    unittest.main()
