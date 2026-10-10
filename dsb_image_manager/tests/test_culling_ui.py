from __future__ import annotations

import os
import tempfile
import tkinter as tk
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dsb_image_manager.dsb_image_manager.core.models import ImageRecord
from dsb_image_manager.dsb_image_manager.services.catalog import Catalog
from dsb_image_manager.dsb_image_manager.services.scanner import ImageScanner
from dsb_image_manager.dsb_image_manager.ui import tk_app

from test_operation_lifecycle import FastMetadata, make_record


def rec(media="jpg", pair="jpg_only", pick="Unrated", rating=0, ext=".jpg"):
    return ImageRecord(1, Path("C:/x/IMG_1.CR3"), ext, "IMG_1", media, "IMG_1", pair, None, None, None,
                       datetime(2026, 9, 5, 10, 12, 33), datetime(2026, 9, 6), pick_status=pick, rating=rating)


class HelperTests(unittest.TestCase):
    def test_model_display_helpers(self):
        raw = rec("raw", "raw_jpg_pair", "Pick", ext=".cr3")
        self.assertEqual((raw.type_label, raw.short_datetime, raw.pick_glyph), ("RAW", "09-05 10:12", "\u2713"))
        self.assertEqual(rec().type_label, "JPG")
        self.assertEqual([rec(pick=p).pick_glyph for p in ("Maybe", "Reject", "Unrated")], ["?", "\u2715", ""])

    def test_filter_labels_map_to_existing_internal_values(self):
        self.assertEqual(tk_app.value_for(tk_app.FILE_FILTER_LABELS, "Pairs (RAW+JPG)"), "paired")
        self.assertEqual(tk_app.value_for(tk_app.FILE_FILTER_LABELS, "Unpaired RAW"), "raw_only")
        self.assertEqual(tk_app.value_for(tk_app.FILE_FILTER_LABELS, "RAW only"), "raw")
        self.assertEqual(tk_app.label_for(tk_app.FILE_FILTER_LABELS, "proxy_failed"), "Preview failed")
        self.assertEqual(tk_app.value_for(tk_app.RATING_FILTER_LABELS, "3\u2605+"), "3")

    def test_filter_match_and_texts(self):
        self.assertTrue(tk_app.record_matches_filters(rec(pick="Pick", rating=3), "Pick", 3))
        self.assertFalse(tk_app.record_matches_filters(rec(pick="Maybe", rating=3), "Pick", 0))
        self.assertFalse(tk_app.record_matches_filters(rec(pick="Pick", rating=2), "all", 3))
        self.assertEqual(tk_app.progress_text("scan", 18, 42, "IMG_1010.JPG"), "Scanning 18/42 \u2014 IMG_1010.JPG")
        self.assertEqual(tk_app.ready_status_text(42, 24), "Ready. 42 files (24 shots)")
        self.assertEqual(tk_app.send_confirm_text(12, "JPG", "Auto Selector"), "Send 12 picked JPGs to Auto Selector?")
        self.assertIn("(2 RAW, 1 JPG)", tk_app.backup_confirm_text(
            [rec("raw"), rec("raw"), rec("jpg")], "D:/out"))
        self.assertIn("3 selected / 9 shown", tk_app.selection_status_text(3, 9))
        self.assertEqual(tk_app.position_text(11, 42), "12 / 42")
        self.assertIn("view the JPG of this pair", tk_app.preview_unavailable_text(rec("raw", "raw_jpg_pair")))

    def test_operation_summary_wording(self):
        summary = SimpleNamespace(copied=3, exported=0, written=0, skipped=0, errors=0, cancelled=False)
        self.assertEqual(tk_app.operation_summary_text("backup", summary, "D:\\b"),
                         "Backed up 3 files to D:\\b (0 skipped, 0 errors)")

    def test_empty_state_kind(self):
        kind = tk_app.empty_state_kind
        self.assertEqual(kind(False, False, 0, False), "start")
        self.assertIsNone(kind(False, True, 0, False))
        self.assertEqual(kind(True, False, 0, True), "filtered")
        self.assertEqual(kind(True, False, 0, False), "empty")
        self.assertIsNone(kind(True, False, 5, True))


class CullingUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"LOCALAPPDATA": str(root / "appdata")})
        env.start()
        self.addCleanup(env.stop)
        source = root / "source"
        for index in range(5):
            make_record(source / f"{index}.jpg", index)
        result = ImageScanner(FastMetadata()).scan(source)
        catalog = Catalog(result.catalog_path)
        catalog.update_selections([r.id for r in result.records], pick_status="Unrated", rating=0)
        catalog.close()
        try:
            self.app = tk_app.ImageManagerApp()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.addCleanup(self.app.destroy)
        self.app.attributes("-alpha", 0)
        self.app.source_dir = source
        self.app._scan_finished(result.catalog_path)
        self.app.update()
        self.assertIn("Ready. 5 files (5 shots)", self.app.status.get())

    def rows(self):
        return list(self.app.tree.get_children())

    def index(self):
        return self.rows().index(self.app.tree.selection()[0])

    def test_one_down_key_moves_exactly_one_row(self):
        self.app.tree.focus_force()
        self.app.update()
        if self.app.focus_get() is not self.app.tree:
            self.skipTest("Tk could not give the tree keyboard focus")
        self.assertEqual(self.index(), 0)
        self.app.tree.event_generate("<Down>")
        self.app.update()
        self.assertEqual(self.index(), 1)
        self.app.tree.event_generate("<Up>")
        self.app.update()
        self.assertEqual(self.index(), 0)

    def test_arrow_handler_moves_one_row_and_ignores_text_inputs(self):
        tree_event = SimpleNamespace(widget=self.app.tree, state=0)
        self.assertEqual(self.app._on_arrow(tree_event, 1), "break")
        self.assertEqual(self.index(), 1)
        combo_event = SimpleNamespace(widget=self.app.file_filter_widget, state=0)
        self.assertIsNone(self.app._on_arrow(combo_event, 1))
        self.assertEqual(self.index(), 1)
        self.assertIsNone(self.app._on_arrow(SimpleNamespace(widget=self.app.tree, state=0x1), 1))

    def test_filter_keyboard_input_does_not_mark_or_select_photos(self):
        app = self.app
        app.rating_filter_widget.focus_force()
        app.update()
        if app.focus_get() is not app.rating_filter_widget:
            self.skipTest("Tk could not give the filter keyboard focus")
        selected = app.tree.selection()
        for key in ("3", "p", "x", "<Control-a>"):
            with self.subTest(key=key):
                app.rating_filter_widget.event_generate(key)
                app.update()
                self.assertEqual(app.tree.selection(), selected)
                self.assertTrue(all(r.rating == 0 and r.pick_status == "Unrated"
                                    for r in app.catalog.list_images()))

    def test_photo_shortcuts_still_mark_and_advance_from_the_tree(self):
        app = self.app
        app.tree.focus_force()
        app.update()
        if app.focus_get() is not app.tree:
            self.skipTest("Tk could not give the tree keyboard focus")
        app.tree.event_generate("p")
        app.update()
        self.assertEqual(self.index(), 1)
        self.assertEqual(app.records[0].pick_status, "Pick")
        app.tree.event_generate("3")
        app.update()
        self.assertEqual(self.index(), 2)
        self.assertEqual(app.records[1].rating, 3)

    def test_auto_advance_after_pick_and_setting_off(self):
        self.app.set_pick("Pick")
        self.assertEqual(self.index(), 1)
        self.assertEqual(self.app.tree.set(self.rows()[0], "state"), "\u2713")
        self.app.advance_after_mark.set(False)
        self.app.set_rating(4)
        self.assertEqual(self.index(), 1)
        self.assertEqual(self.app.current_record.rating, 4)
        self.app.advance_after_mark.set(True)
        self.app.tree.selection_set(self.rows()[1:3])
        self.app.tree.focus(self.rows()[1])
        self.app.on_select()
        self.app.set_pick("Reject")
        self.assertEqual([r.pick_status for r in self.app.records[1:3]], ["Reject", "Reject"])
        self.assertEqual(len(self.app.tree.selection()), 2)

    def test_visible_mark_buttons_keep_advance_and_batch_selection_semantics(self):
        app = self.app
        app.mark_buttons["Pick"].invoke()
        self.assertEqual(self.index(), 1)
        self.assertEqual(app.records[0].pick_status, "Pick")
        app.advance_after_mark.set(False)
        app.mark_buttons["Maybe"].invoke()
        self.assertEqual(self.index(), 1)
        self.assertEqual(app.current_record.pick_status, "Maybe")
        app.set_rating(4, advance=False)
        app.mark_buttons["Unrated"].invoke()
        self.assertEqual((app.current_record.pick_status, app.current_record.rating), ("Unrated", 4))
        app.tree.selection_set(self.rows()[1:3])
        app.on_select()
        app.mark_buttons["Reject"].invoke()
        self.assertEqual([r.pick_status for r in app.records[1:3]], ["Reject", "Reject"])
        self.assertEqual(len(app.tree.selection()), 2)

    def test_culling_buttons_disable_during_work_and_restore_afterwards(self):
        app = self.app
        buttons = (*app.mark_buttons.values(), app.export_button, app.send_selector_button, app.send_frame_button)
        app._active_job = "backup"
        app._set_work_controls(True)
        self.assertTrue(all(str(button.cget("state")) == "disabled" for button in buttons))
        app.mark_buttons["Pick"].invoke()
        self.assertTrue(all(record.pick_status == "Unrated" for record in app.records))
        app._active_job = None
        app._set_work_controls(False)
        self.assertTrue(all(str(button.cget("state")) == "normal" for button in buttons))
        app.tree.selection_remove(*app.tree.selection())
        app.on_select()
        self.assertTrue(all(str(button.cget("state")) == "disabled"
                            for button in (*app.mark_buttons.values(), app.export_button)))

    def test_visible_handoff_buttons_keep_confirmation(self):
        app = self.app
        app.mark_buttons["Pick"].invoke()
        with patch.object(tk_app.messagebox, "askyesno", return_value=False) as confirm, \
                patch.object(tk_app, "launch_app") as launch:
            app.send_selector_button.invoke()
            self.assertEqual(confirm.call_args.args[0], "Send Picks to Auto Selector")
            app.send_frame_button.invoke()
            self.assertEqual(confirm.call_args.args[0], "Send Picks to Frame")
        launch.assert_not_called()

    def test_marks_update_in_place_without_rebuilding(self):
        with patch.object(self.app, "refresh_records") as refresh:
            self.app.set_pick("Maybe")
            refresh.assert_not_called()
        self.assertEqual(self.app.tree.set(self.rows()[0], "pick"), "Maybe")

    def test_row_leaving_filter_stays_until_navigation(self):
        self.app.pick_filter.set("Unrated")
        self.app.refresh_records()
        self.assertEqual(len(self.rows()), 5)
        self.app.advance_after_mark.set(False)
        self.app.set_pick("Pick")
        self.assertEqual(len(self.rows()), 5)
        self.app.move_selection(1)
        self.assertEqual(len(self.rows()), 4)
        self.assertEqual(len(self.app.records), 4)

    def test_filter_with_no_match_shows_clear_filters_message(self):
        self.app.rating_filter.set("5")
        self.app.refresh_records()
        self.app.update()
        self.assertEqual(self.app.empty_label.cget("text"), "No photos match these filters.")
        self.assertEqual(self.app.empty_button.cget("text"), "Clear Filters")
        self.assertTrue(self.app.empty_overlay.winfo_ismapped())
        self.app.clear_filters()
        self.app.update()
        self.assertFalse(self.app.empty_overlay.winfo_ismapped())
        self.assertEqual(len(self.rows()), 5)

    def test_advance_setting_is_persisted(self):
        self.app.advance_after_mark.set(False)
        self.app._save_advance_setting()
        from ndex_common.settings import get_section

        self.assertIs(get_section(tk_app.SETTINGS_SECTION)["advance_after_mark"], False)


if __name__ == "__main__":
    unittest.main()
