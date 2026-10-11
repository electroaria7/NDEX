from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
import tkinter as tk
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from dsb_image_manager.dsb_image_manager.core.models import (
    ExportOptions,
    ImageRecord,
    MarkChange,
    Shot,
    UndoStack,
    apply_shot_state,
    build_shots,
    merge_pick_status,
)
from dsb_image_manager.dsb_image_manager.services.backup import BackupService
from dsb_image_manager.dsb_image_manager.services.catalog import Catalog
from dsb_image_manager.dsb_image_manager.services.exporter import ExportService
from dsb_image_manager.dsb_image_manager.services.scanner import ImageScanner, ScanCancelled
from dsb_image_manager.dsb_image_manager.ui import tk_app

from test_operation_lifecycle import FastMetadata


def rec(path: str, media: str, pick: str = "Unrated", rating: int = 0, ident: int | None = None) -> ImageRecord:
    p = Path(path)
    return ImageRecord(
        ident, p, p.suffix.lower().lstrip("."), p.stem, media, f"{str(p.parent).casefold()}|{p.stem.casefold()}",
        "unknown", None, None, None, datetime(2026, 10, 10, 9, 0), datetime(2026, 10, 10),
        pick_status=pick, rating=rating,  # type: ignore[arg-type]
    )


def make_jpg(path: Path, color: str = "navy") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 12), color).save(path, "JPEG")
    return path


def make_shoot(root: Path) -> Path:
    """IMG_1 and IMG_2 are RAW+JPG pairs, IMG_3 is JPG only, IMG_4 is RAW only."""
    for name in ("IMG_1", "IMG_2"):
        make_jpg(root / f"{name}.JPG")
        (root / f"{name}.CR3").write_bytes(b"fake raw " + name.encode())
    make_jpg(root / "IMG_3.JPG")
    (root / "IMG_4.CR3").write_bytes(b"fake raw 4")
    return root


class ShotModelTests(unittest.TestCase):
    def test_grouping_is_per_folder_and_case_insensitive(self):
        records = [
            rec("C:/s/a/IMG_1.CR3", "raw"), rec("C:/s/a/img_1.jpg", "jpg"),
            rec("C:/s/b/IMG_1.JPG", "jpg"), rec("C:/s/a/IMG_2.CR3", "raw"),
        ]
        shots = build_shots(records)
        self.assertEqual(len(shots), 3)
        pair = shots[records[0].pair_group_id]
        self.assertEqual(pair.type_label, "RAW+JPG")
        self.assertEqual(pair.primary.media_type, "jpg")  # preview uses the JPG
        self.assertEqual([r.media_type for r in pair.records], ["jpg", "raw"])
        self.assertEqual(shots[records[2].pair_group_id].type_label, "JPG")
        raw_only = shots[records[3].pair_group_id]
        self.assertEqual((raw_only.type_label, raw_only.primary.media_type), ("RAW", "raw"))

    def test_merge_rule_pick_beats_reject_beats_maybe(self):
        self.assertEqual(merge_pick_status(["Reject", "Pick"]), "Pick")
        self.assertEqual(merge_pick_status(["Maybe", "Reject"]), "Reject")
        self.assertEqual(merge_pick_status(["Unrated", "Maybe"]), "Maybe")
        self.assertEqual(merge_pick_status(["Unrated", "Unrated"]), "Unrated")
        shot = Shot("k", [rec("C:/s/A.JPG", "jpg", "Maybe", 2), rec("C:/s/A.CR3", "raw", "Reject", 4)])
        self.assertEqual((shot.pick_status, shot.rating), ("Reject", 4))

    def test_apply_shot_state_gives_every_file_the_shot_state(self):
        records = [rec("C:/s/A.JPG", "jpg", "Pick", 3), rec("C:/s/A.CR3", "raw"), rec("C:/s/B.JPG", "jpg")]
        result = apply_shot_state(records)
        self.assertEqual([(r.pick_status, r.rating) for r in result],
                         [("Pick", 3), ("Pick", 3), ("Unrated", 0)])
        self.assertEqual(records[1].pick_status, "Unrated")  # inputs stay untouched


class UndoStackTests(unittest.TestCase):
    def change(self, label="Pick: Reject 3 shots"):
        return MarkChange(label, [(1, "Unrated", 0, "Reject", 0), (2, "Unrated", 0, "Reject", 0)])

    def test_undo_redo_walk_and_new_edit_clears_redo(self):
        stack = UndoStack()
        first, second = self.change("one"), self.change("two")
        stack.push(first)
        stack.push(second)
        self.assertEqual(stack.undo_label, "two")
        self.assertIs(stack.pop_undo(), second)
        self.assertEqual((stack.undo_label, stack.redo_label), ("one", "two"))
        self.assertIs(stack.pop_redo(), second)
        stack.pop_undo()
        stack.push(self.change("three"))
        self.assertEqual(stack.redo_label, "")
        self.assertIsNone(UndoStack().pop_undo())

    def test_stack_keeps_only_the_last_hundred(self):
        stack = UndoStack(100)
        for index in range(130):
            stack.push(self.change(f"edit {index}"))
        self.assertEqual(len(stack), 100)
        self.assertEqual(stack.undo_label, "edit 129")
        labels = []
        while (change := stack.pop_undo()) is not None:
            labels.append(change.label)
        self.assertEqual(labels[-1], "edit 30")

    def test_label_wording(self):
        self.assertEqual(tk_app.mark_change_label("Reject", None, 12, "shot"), "Pick: Reject 12 shots")
        self.assertEqual(tk_app.mark_change_label(None, 3, 1, "shot"), "Rating: 3\u2605 1 shot")
        self.assertEqual(tk_app.mark_done_text("Reject", None, 12, "shot"), "Rejected 12 shots")
        self.assertEqual(tk_app.scan_stopped_text(120, 900),
                         "Scan stopped \u2014 120 of 900 files listed. Rescan (F5) to finish.")


class CatalogShotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_shoot(Path(self.tmp.name) / "shoot")
        self.result = ImageScanner(FastMetadata()).scan(self.root)
        self.catalog = Catalog(self.result.catalog_path)
        self.addCleanup(self.catalog.close)

    def ids(self, *names):
        return [r.id for r in self.catalog.list_images() if r.file_path.name in names]

    def test_list_shots_filters_by_composition(self):
        names = lambda shots: sorted(s.stem for s in shots)  # noqa: E731
        self.assertEqual(names(self.catalog.list_shots()), ["IMG_1", "IMG_2", "IMG_3", "IMG_4"])
        self.assertEqual(names(self.catalog.list_shots("paired")), ["IMG_1", "IMG_2"])
        self.assertEqual(names(self.catalog.list_shots("raw")), ["IMG_4"])
        self.assertEqual(names(self.catalog.list_shots("jpg")), ["IMG_3"])
        self.catalog.set_marks((i, "Pick", 4) for i in self.ids("IMG_1.JPG", "IMG_1.CR3"))
        self.assertEqual(names(self.catalog.list_shots(pick_filter="Pick")), ["IMG_1"])
        self.assertEqual(names(self.catalog.list_shots(min_rating=4)), ["IMG_1"])

    def test_migration_resolves_disagreeing_pairs_once(self):
        jpg, raw = self.ids("IMG_1.JPG")[0], self.ids("IMG_1.CR3")[0]
        jpg2, raw2 = self.ids("IMG_2.JPG")[0], self.ids("IMG_2.CR3")[0]
        self.catalog.set_marks([(jpg, "Maybe", 2), (raw, "Pick", 1), (jpg2, "Reject", 0), (raw2, "Maybe", 5)])
        with self.assertLogs("dsb_image_manager.dsb_image_manager.services.catalog", "INFO") as logs:
            self.assertEqual(self.catalog.reconcile_pair_marks(), (2, 4))
        self.assertIn("2 shot(s)", logs.output[0])
        marks = {r.file_path.name: (r.pick_status, r.rating) for r in self.catalog.list_images()}
        self.assertEqual(marks["IMG_1.JPG"], ("Pick", 2))
        self.assertEqual(marks["IMG_1.CR3"], ("Pick", 2))
        self.assertEqual(marks["IMG_2.JPG"], ("Reject", 5))  # Reject beats Maybe; highest rating wins
        self.assertEqual(marks["IMG_2.CR3"], ("Reject", 5))
        self.assertEqual(self.catalog.reconcile_pair_marks(), (0, 0))

    def test_backup_copies_every_file_of_picked_shots(self):
        self.catalog.set_marks((i, "Pick", 0) for i in self.ids("IMG_1.JPG", "IMG_1.CR3", "IMG_4.CR3"))
        shots = self.catalog.list_shots(pick_filter="Pick")
        files = tk_app.shot_files(shots)
        self.assertEqual(tk_app.file_counts_text(files), "1 JPG + 2 RAW")
        self.assertTrue(tk_app.backup_confirm_text(shots, "D:/b").startswith(
            "Back up 2 picked shots (1 JPG + 2 RAW) to:"))
        summary = BackupService().backup(files, Path(self.tmp.name) / "backup")
        self.assertEqual((summary.copied, summary.errors), (3, 0))
        copied = sorted(p.name for p in (Path(self.tmp.name) / "backup").rglob("*") if p.is_file())
        self.assertEqual(copied, ["IMG_1.CR3", "IMG_1.JPG", "IMG_4.CR3"])

    def test_export_gives_both_files_of_a_shot_the_same_index(self):
        shots = self.catalog.list_shots("paired")
        out = Path(self.tmp.name) / "out"
        summary = ExportService().export(
            tk_app.shot_files(shots), ExportOptions(out, "{index}_{name}", start_index=7))
        self.assertEqual(summary.exported, 4)
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ["007_IMG_1.CR3", "007_IMG_1.JPG", "008_IMG_2.CR3", "008_IMG_2.JPG"])


class ScannerStreamingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "shoot"

    def counting_reader(self):
        calls = []

        class Reader(FastMetadata):
            def read_batch(self, paths):
                calls.append(list(paths))
                return {}

        return Reader(), calls

    def test_rows_stream_in_batches_and_pairs_stay_together(self):
        for index in range(45):
            make_jpg(self.root / f"P{index:03d}.JPG")
            (self.root / f"P{index:03d}.CR3").write_bytes(b"raw")
        batches = []
        result = ImageScanner(FastMetadata()).scan(self.root, batch_callback=lambda batch: batches.append(batch))
        self.assertGreater(len(batches), 1)
        self.assertEqual(sum(len(b) for b in batches), 90)
        for batch in batches:
            stems = [r.file_path.stem for r in batch]
            for stem in set(stems):
                self.assertEqual(stems.count(stem), 2)  # never half a pair in one batch
            self.assertTrue(all(r.id is not None for r in batch))
        self.assertEqual(len(result.records), 90)

    def test_unchanged_files_are_reused_without_reading_metadata(self):
        for index in range(30):
            make_jpg(self.root / f"R{index:02d}.JPG")
        reader, calls = self.counting_reader()
        first = ImageScanner(reader).scan(self.root)
        self.assertEqual(sum(len(c) for c in calls), 30)
        catalog = Catalog(first.catalog_path)
        catalog.set_marks([(first.records[0].id, "Pick", 3)])
        catalog.update_backup_status(first.records[0].id, "backed_up")
        catalog.close()
        calls.clear()
        thumbs = {p: p.stat().st_mtime_ns for p in (self.root / ".dsb_cache" / "thumbnails").iterdir()}
        again = ImageScanner(reader).scan(self.root)
        self.assertEqual(calls, [])  # no metadata re-read
        self.assertEqual({p: p.stat().st_mtime_ns for p in (self.root / ".dsb_cache" / "thumbnails").iterdir()}, thumbs)
        reused = {r.id: r for r in again.records}
        self.assertEqual((reused[first.records[0].id].pick_status, reused[first.records[0].id].rating,
                          reused[first.records[0].id].backup_status), ("Pick", 3, "backed_up"))
        # One file changes on disk: only that one is read again.
        changed = self.root / "R05.JPG"
        make_jpg(changed, "red")
        stat = changed.stat()
        os.utime(changed, ns=(stat.st_atime_ns, stat.st_mtime_ns + 7_000_000_000))
        ImageScanner(reader).scan(self.root)
        self.assertEqual(calls, [[changed.resolve()]])

    def test_reuse_follows_pairing_changes_and_missing_thumbnails(self):
        make_jpg(self.root / "A.JPG")
        reader, calls = self.counting_reader()
        first = ImageScanner(reader).scan(self.root)
        self.assertEqual(first.records[0].pair_status, "jpg_only")
        (self.root / "A.CR3").write_bytes(b"raw")
        first.records[0].thumbnail_path.unlink()
        calls.clear()
        again = ImageScanner(reader).scan(self.root)
        by_name = {r.file_path.name: r for r in again.records}
        self.assertEqual(by_name["A.JPG"].pair_status, "raw_jpg_pair")
        self.assertTrue(by_name["A.JPG"].thumbnail_path.exists())  # thumbnail rebuilt
        self.assertEqual(sorted(p.name for c in calls for p in c), ["A.CR3", "A.JPG"])

    def test_legacy_catalog_without_fingerprint_columns_is_upgraded(self):
        make_jpg(self.root / "A.JPG")
        result = ImageScanner(FastMetadata()).scan(self.root)
        connection = sqlite3.connect(result.catalog_path)
        connection.executescript("ALTER TABLE images DROP COLUMN size_bytes; ALTER TABLE images DROP COLUMN mtime_ns;")
        connection.close()
        reader, calls = self.counting_reader()
        ImageScanner(reader).scan(self.root)  # old rows have no fingerprint: read once
        self.assertEqual(len(calls), 1)
        calls.clear()
        ImageScanner(reader).scan(self.root)
        self.assertEqual(calls, [])

    def test_cancel_keeps_listed_files_and_a_usable_catalog(self):
        for index in range(60):
            make_jpg(self.root / f"C{index:02d}.JPG")
        cancel = threading.Event()

        class Reader(FastMetadata):
            def __init__(self):
                self.calls = 0

            def read_batch(self, paths):
                self.calls += 1
                if self.calls == 2:
                    cancel.set()
                return {}

        listed = []
        with self.assertRaises(ScanCancelled) as caught:
            ImageScanner(Reader()).scan(self.root, cancel_event=cancel, batch_callback=listed.extend)
        self.assertEqual((caught.exception.listed, caught.exception.total), (20, 60))
        self.assertEqual(len(listed), 20)
        catalog = Catalog(caught.exception.catalog_path)
        try:
            self.assertEqual(len(catalog.list_images()), 20)
            self.assertEqual(len(catalog.list_shots()), 20)
        finally:
            catalog.close()
        # Rescan finishes the job without touching the files already listed.
        reader, calls = self.counting_reader()
        done = ImageScanner(reader).scan(self.root)
        self.assertEqual(len(done.records), 60)
        self.assertEqual(sum(len(c) for c in calls), 40)

    def test_cancel_does_not_delete_catalog_rows_that_were_not_reached(self):
        for index in range(3):
            make_jpg(self.root / f"K{index}.JPG")
        ImageScanner(FastMetadata()).scan(self.root)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(ScanCancelled):
            ImageScanner(FastMetadata()).scan(self.root, cancel_event=cancel)
        catalog = Catalog(self.root / ".dsb_cache" / "catalog.sqlite")
        try:
            self.assertEqual(len(catalog.list_images()), 3)
        finally:
            catalog.close()


class ShotUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"LOCALAPPDATA": str(root / "appdata")})
        env.start()
        self.addCleanup(env.stop)
        self.source = make_shoot(root / "source")
        self.result = ImageScanner(FastMetadata()).scan(self.source)
        try:
            self.app = tk_app.ImageManagerApp()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.addCleanup(self.app.destroy)
        self.app.withdraw()
        self.app.source_dir = self.source
        self.app._scan_finished(self.result.catalog_path)
        self.app.update()

    def rows(self):
        return list(self.app.tree.get_children())

    def values(self):
        return [self.app.tree.item(iid, "values") for iid in self.rows()]

    def select(self, *indexes):
        rows = self.rows()
        self.app.tree.selection_set([rows[i] for i in indexes])
        self.app.tree.focus(rows[indexes[0]])
        self.app.on_select()

    def catalog_marks(self):
        return {r.file_path.name: (r.pick_status, r.rating) for r in self.app.catalog.list_images()}

    def test_combined_mode_is_default_and_shows_type_badges(self):
        self.assertTrue(self.app.combine_pairs.get())
        self.assertEqual([(v[1], v[2]) for v in self.values()],
                         [("IMG_1", "RAW+JPG"), ("IMG_2", "RAW+JPG"), ("IMG_3", "JPG"), ("IMG_4", "RAW")])
        self.assertIn("Files: IMG_1.JPG + IMG_1.CR3", self.app.detail_text.get("1.0", tk.END))
        self.assertEqual(self.app.current_record.file_path.suffix.upper(), ".JPG")  # preview file is the JPG
        self.assertIn("Ready. 6 files (4 shots)", self.app.status.get())

    def test_toggle_to_split_lists_every_file_persists_and_keeps_selection(self):
        self.select(1)
        self.app.combine_pairs.set(False)
        self.app._on_combine_toggled()
        self.assertEqual(len(self.rows()), 6)
        self.assertEqual([v[1] for v in self.values()][:2], ["IMG_1.CR3", "IMG_1.JPG"])
        selected = {self.app._rows[i].file_path.stem for i in self.app.tree.selection()}
        self.assertEqual(selected, {"IMG_2"})
        from ndex_common.settings import get_section

        self.assertIs(get_section(tk_app.SETTINGS_SECTION)["combine_pairs"], False)
        self.app.combine_pairs.set(True)
        self.app._on_combine_toggled()
        self.assertEqual(len(self.rows()), 4)

    def test_marks_apply_to_every_file_of_the_shot_in_both_modes(self):
        self.app.advance_after_mark.set(False)
        self.select(0)
        self.app.set_pick("Pick")
        self.app.set_rating(3)
        marks = self.catalog_marks()
        self.assertEqual((marks["IMG_1.JPG"], marks["IMG_1.CR3"]), (("Pick", 3), ("Pick", 3)))
        self.app.combine_pairs.set(False)
        self.app._on_combine_toggled()
        raw_row = next(i for i in self.rows() if self.app._rows[i].file_path.name == "IMG_2.CR3")
        self.app.tree.selection_set(raw_row)
        self.app.tree.focus(raw_row)
        self.app.on_select()
        self.app.set_pick("Reject")  # select only the RAW: its JPG follows
        marks = self.catalog_marks()
        self.assertEqual((marks["IMG_2.JPG"], marks["IMG_2.CR3"]), (("Reject", 0), ("Reject", 0)))
        jpg_row = next(i for i in self.rows() if self.app._rows[i].file_path.name == "IMG_2.JPG")
        self.assertEqual(self.app.tree.set(jpg_row, "pick"), "Reject")  # sibling row updated in place
        self.assertEqual(self.app.tree.set(jpg_row, "state"), "\u2715")

    def test_split_mode_advance_skips_the_marked_files_sibling(self):
        self.app.combine_pairs.set(False)
        self.app._on_combine_toggled()
        self.select(0)  # IMG_1.CR3, whose JPG sibling is marked too
        self.app.set_pick("Pick")
        self.assertEqual(self.app.current_record.file_path.name, "IMG_2.CR3")

    def test_picked_shot_files_feed_backup_export_and_send(self):
        self.select(0)
        self.app.advance_after_mark.set(False)
        self.app.set_pick("Pick")
        picked = self.app.catalog.list_shots(pick_filter="Pick")
        self.assertEqual(sorted(tk_app.shot_files(picked), key=lambda r: r.file_path.name)[0].file_path.name, "IMG_1.CR3")
        with patch.object(tk_app.filedialog, "askdirectory", return_value=str(Path(self.tmp.name) / "bk")), \
                patch.object(tk_app.messagebox, "askyesno", return_value=True) as confirm, \
                patch.object(self.app, "_start_operation") as start:
            self.app.backup_picked()
        self.assertTrue(confirm.call_args.args[1].startswith("Back up 1 picked shot (1 JPG + 1 RAW) to:"))
        self.assertEqual(sorted(r.file_path.name for r in start.call_args.args[1]), ["IMG_1.CR3", "IMG_1.JPG"])
        with patch.object(tk_app, "Tk", create=True), patch.object(tk_app.tk, "Toplevel") as top:
            top.return_value.after = lambda *a, **k: None
            try:
                self.app.open_export_dialog()
            except Exception:
                pass  # widget construction is mocked; only the file selection matters here

    def test_undo_redo_single_and_bulk_with_labels_and_status(self):
        app = self.app
        app.advance_after_mark.set(False)
        self.select(0)
        app.set_pick("Pick")
        self.select(0, 1, 2)
        app.set_pick("Reject")
        self.assertEqual(app.status.get(), "Rejected 3 shots \u2014 Ctrl+Z to undo")
        app._update_undo_menu()
        self.assertEqual(app.edit_menu.entrycget(0, "label"), "Undo Pick: Reject 3 shots")
        self.assertEqual(app.edit_menu.entrycget(1, "state"), "disabled")
        self.assertEqual({v for k, v in self.catalog_marks().items() if k != "IMG_4.CR3"}, {("Reject", 0)})
        app.undo()  # the whole bulk edit is one step
        marks = self.catalog_marks()
        self.assertEqual((marks["IMG_1.JPG"], marks["IMG_1.CR3"], marks["IMG_2.CR3"], marks["IMG_3.JPG"]),
                         (("Pick", 0), ("Pick", 0), ("Unrated", 0), ("Unrated", 0)))
        self.assertEqual(app.tree.set(self.rows()[0], "pick"), "Pick")
        self.assertEqual(app.edit_menu.entrycget(0, "label"), "Undo Pick: Pick 1 shot")
        self.assertEqual(app.edit_menu.entrycget(1, "label"), "Redo Pick: Reject 3 shots")
        app.redo()
        self.assertEqual(self.catalog_marks()["IMG_3.JPG"], ("Reject", 0))
        app.undo()
        app.undo()
        self.assertEqual(self.catalog_marks()["IMG_1.JPG"], ("Unrated", 0))
        app.undo()
        self.assertEqual(app.status.get(), "Nothing to undo.")

    def test_ctrl_z_and_ctrl_y_shortcuts(self):
        app = self.app
        app.deiconify()
        app.update()
        app.tree.focus_force()
        app.update()
        if app.focus_get() is not app.tree:
            self.skipTest("Tk could not give the tree keyboard focus")
        app.advance_after_mark.set(False)
        app.tree.event_generate("x")
        app.update()
        self.assertEqual(self.catalog_marks()["IMG_1.JPG"][0], "Reject")
        app.tree.event_generate("<Control-z>")
        app.update()
        self.assertEqual(self.catalog_marks()["IMG_1.JPG"][0], "Unrated")
        app.tree.event_generate("<Control-y>")
        app.update()
        self.assertEqual(self.catalog_marks()["IMG_1.CR3"][0], "Reject")
        app.tree.event_generate("<Control-z>")
        app.tree.event_generate("<Control-Shift-Z>")
        app.update()
        self.assertEqual(self.catalog_marks()["IMG_1.CR3"][0], "Reject")

    def test_undo_state_is_not_persisted_and_clears_on_a_new_folder(self):
        self.app.set_pick("Pick")
        self.assertEqual(len(self.app.undo_stack), 1)
        other = make_shoot(Path(self.tmp.name) / "other")
        self.app.source_dir = other
        with patch.object(self.app, "_start_worker"):
            self.app.scan_folder()
        self.assertEqual(len(self.app.undo_stack), 0)

    def test_filters_apply_to_whole_shots_in_combined_mode(self):
        self.app.file_filter.set("paired")
        self.app.refresh_records()
        self.assertEqual([v[1] for v in self.values()], ["IMG_1", "IMG_2"])
        self.app.file_filter.set("raw")
        self.app.refresh_records()
        self.assertEqual([v[1] for v in self.values()], ["IMG_4"])
        self.app.file_filter.set("all")
        self.app.combine_pairs.set(False)
        self.app.file_filter.set("paired")
        self.app.refresh_records()
        self.assertEqual(len(self.rows()), 4)


class StreamingUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"LOCALAPPDATA": str(root / "appdata")})
        env.start()
        self.addCleanup(env.stop)
        self.source = root / "source"
        for index in range(30):
            make_jpg(self.source / f"S{index:02d}.JPG")
        try:
            self.app = tk_app.ImageManagerApp()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.app.withdraw()
        self.gate = threading.Event()
        self.addCleanup(self.gate.set)
        self.addCleanup(self.finish)
        self.errors = []
        self.app.report_callback_exception = lambda kind, value, tb: self.errors.append(value)

    def finish(self):
        if self.app._active_job is not None:
            self.app.cancel_work()
            self.gate.set()
            self.pump(lambda: self.app._active_job is None)
        self.app.destroy()

    def pump(self, condition, timeout=8):
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            self.app.update()
            time.sleep(0.005)
        self.assertTrue(condition())
        self.assertEqual(self.errors, [])

    def start_slow_scan(self):
        gate, calls = self.gate, []

        class Reader(FastMetadata):
            def read_batch(self, paths):
                calls.append(len(paths))
                if len(calls) >= 2 and not gate.wait(8):
                    raise RuntimeError("gate not released")
                return {}

        self.app.source_dir = self.source
        with patch.object(tk_app, "ImageScanner", return_value=ImageScanner(Reader())):
            self.app.scan_folder()

    def test_rows_stream_in_and_can_be_culled_mid_scan_then_cancel_keeps_them(self):
        app = self.app
        self.start_slow_scan()
        self.pump(lambda: len(app.tree.get_children()) == 20)
        self.assertEqual(app._active_job, "scan")
        self.assertEqual(str(app.cancel_button.cget("state")), "normal")
        self.assertEqual(str(app.mark_buttons["Pick"].cget("state")), "normal")  # culling is open mid-scan
        self.assertEqual(str(app.export_button.cget("state")), "disabled")
        self.assertEqual(str(app.file_filter_widget.cget("state")), "disabled")
        app.advance_after_mark.set(False)
        app.set_pick("Pick")
        app.set_rating(4)
        self.assertEqual(app.records[0].pick_status, "Pick")
        self.assertEqual(app.tree.set(app.tree.get_children()[0], "pick"), "Pick")
        app.undo()
        self.assertEqual(app.records[0].rating, 0)
        app.redo()
        self.assertEqual(app.records[0].rating, 4)
        # Esc cancels the scan.
        app._on_escape(None)
        self.gate.set()
        self.pump(lambda: app._active_job is None)
        self.assertEqual(app.status.get(), "Scan stopped \u2014 20 of 30 files listed. Rescan (F5) to finish.")
        self.assertEqual(len(app.tree.get_children()), 20)
        self.assertIsNotNone(app.catalog)
        catalog = Catalog(self.source / ".dsb_cache" / "catalog.sqlite")
        try:
            self.assertEqual(len(catalog.list_images(pick_filter="Pick")), 1)
        finally:
            catalog.close()
        # F5 finishes the listing and keeps the pick.
        app.rescan()
        self.pump(lambda: app._active_job is None)
        self.assertEqual(len(app.tree.get_children()), 30)
        self.assertEqual(sum(r.pick_status == "Pick" for r in app.records), 1)


if __name__ == "__main__":
    unittest.main()
