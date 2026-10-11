from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from dsb_image_manager.dsb_image_manager.core.models import Shot
from dsb_image_manager.dsb_image_manager.services.cache import CacheManager
from dsb_image_manager.dsb_image_manager.services.catalog import Catalog
from dsb_image_manager.dsb_image_manager.services.scanner import ImageScanner
from dsb_image_manager.dsb_image_manager.services.thumbnails import ThumbnailLoader
from dsb_image_manager.dsb_image_manager.ui import grid_model as gm
from dsb_image_manager.dsb_image_manager.ui import tk_app
from ndex_common import i18n
from ndex_common.settings import get_section

from test_operation_lifecycle import FastMetadata, make_record

M = gm.GridMetrics(tile=100, caption=30, gap=10, pad=10)  # cell 110 x 140


class GridModelTests(unittest.TestCase):
    def test_columns_fit_width_and_never_drop_below_one(self):
        self.assertEqual(gm.columns(1, M), 1)
        self.assertEqual(gm.columns(130, M), 1)
        self.assertEqual(gm.columns(2 * 10 + 3 * 110 - 10, M), 3)
        self.assertEqual(gm.columns(2 * 10 + 3 * 110 - 11, M), 2)

    def test_content_height_and_rows(self):
        self.assertEqual(gm.row_count(0, 3), 0)
        self.assertEqual(gm.row_count(7, 3), 3)
        self.assertEqual(gm.content_height(0, 3, M), 0)
        self.assertEqual(gm.content_height(7, 3, M), 3 * 140 - 10 + 20)

    def test_tile_origin_and_hit_test_round_trip(self):
        offset = gm.left_offset(400, 3, M)
        for index in range(8):
            x, y = gm.tile_origin(index, 3, M, offset)
            self.assertEqual(gm.index_at(x + 1, y + 1, 8, 3, M, offset), index)
            self.assertEqual(gm.index_at(x + M.tile - 1, y + M.tile + M.caption - 1, 8, 3, M, offset), index)
        x, y = gm.tile_origin(0, 3, M, offset)
        self.assertIsNone(gm.index_at(x + M.tile + 2, y + 2, 8, 3, M, offset))  # gap
        self.assertIsNone(gm.index_at(1, 1, 8, 3, M, offset) if offset > 1 else None)  # padding
        x, y = gm.tile_origin(8, 3, M, offset)  # empty cell after the last tile
        self.assertIsNone(gm.index_at(x + 1, y + 1, 8, 3, M, offset))

    def test_visible_range_covers_viewport_plus_margin_only(self):
        n, cols = 3000, 4
        first, stop = gm.visible_range(0, 400, n, cols, M, margin_rows=1)
        self.assertEqual(first, 0)
        self.assertEqual(stop, 4 * (400 // 140 + 1 + 1))  # rows 0..3 -> 16 tiles
        first, stop = gm.visible_range(140 * 100 + 10, 400, n, cols, M, margin_rows=1)
        self.assertEqual(first, 99 * cols)  # one margin row above row 100
        self.assertLessEqual(stop - first, cols * 6)
        self.assertEqual(gm.visible_range(10**9, 400, n, cols, M)[1], n)  # clamps at the end
        self.assertEqual(gm.visible_range(0, 400, 0, cols, M), (0, 0))

    def test_virtualization_touches_a_tiny_fraction_of_2000_tiles(self):
        cols = gm.columns(900, M)
        for scroll in (0, 5000, 100000, 10**7):
            first, stop = gm.visible_range(scroll, 700, 2000, cols, M)
            self.assertLess(stop - first, cols * 9)  # 5 visible rows + 1 margin row each side
            self.assertLess(stop - first, 2000 // 20)

    def test_arrow_navigation_indices(self):
        n, cols = 10, 4  # rows: 0-3, 4-7, 8-9
        move = lambda i, key: gm.move_index(i, key, cols, n)  # noqa: E731
        self.assertEqual(move(5, "Right"), 6)
        self.assertEqual(move(9, "Right"), 9)
        self.assertEqual(move(0, "Left"), 0)
        self.assertEqual(move(5, "Left"), 4)
        self.assertEqual(move(5, "Down"), 9)
        self.assertEqual(move(6, "Down"), 9)  # short last row: land on the last tile
        self.assertEqual(move(9, "Down"), 9)
        self.assertEqual(move(8, "Up"), 4)
        self.assertEqual(move(2, "Up"), 2)  # first row stays
        self.assertEqual(gm.arrow_key(1, True), "Down")
        self.assertEqual(gm.arrow_key(-1, True), "Up")
        self.assertEqual(gm.arrow_key(-1, False), "Left")

    def test_scroll_to_reveal_moves_minimally(self):
        n, cols, view = 200, 4, 300
        self.assertEqual(gm.scroll_to_reveal(0, 0, view, n, cols, M), 0)
        # A tile already inside the viewport does not scroll.
        self.assertEqual(gm.scroll_to_reveal(4, 0, view, n, cols, M), 0)
        # Below the viewport: scroll just enough to show its whole caption.
        y = gm.tile_origin(12, cols, M, 0)[1]
        self.assertEqual(gm.scroll_to_reveal(12, 0, view, n, cols, M), y + M.tile + M.caption + M.pad - view)
        # Above the viewport: align the row to the top.
        self.assertEqual(gm.scroll_to_reveal(0, 500, view, n, cols, M), 0)

    def test_top_index_and_scroll_round_trip(self):
        for index in (0, 4, 40, 399):
            scroll = gm.scroll_for_index(index, 4, M)
            self.assertEqual(gm.top_index(scroll, 4, M), (index // 4) * 4)

    def test_range_between_selects_in_list_order_both_directions(self):
        order = [str(i) for i in range(10)]
        self.assertEqual(gm.range_between(order, "2", "5"), ["2", "3", "4", "5"])
        self.assertEqual(gm.range_between(order, "5", "2"), ["2", "3", "4", "5"])
        self.assertEqual(gm.range_between(order, "missing", "3"), ["3"])


class ThumbnailLoaderTests(unittest.TestCase):
    def test_loads_scales_dedupes_and_skips_unwanted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.jpg"
            Image.new("RGB", (420, 420), "red").save(path)
            loader = ThumbnailLoader(workers=1)
            self.addCleanup(loader.close)
            key = (str(path), 64)
            self.assertTrue(loader.request(key))
            self.assertFalse(loader.request(key))  # already queued
            done = []
            deadline = time.time() + 5
            while not done and time.time() < deadline:
                done = loader.drain()
                time.sleep(0.01)
            self.assertEqual(done[0][0], key)
            self.assertEqual(done[0][1].size, (64, 64))
            self.assertEqual(loader.pending(), 0)  # taken by the UI, may be requested again
            # A tile that scrolled away before its turn is not decoded.
            gate_key = (str(path), 32)
            loader.want([])
            with patch("dsb_image_manager.dsb_image_manager.services.thumbnails._decode") as decode:
                loader._wanted.clear()
                loader._inflight.add(gate_key)
                loader._load(gate_key, None)
                decode.assert_not_called()

    def test_missing_file_falls_back_to_rebuilt_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "rebuilt.jpg"
            Image.new("RGB", (50, 50), "blue").save(good)
            loader = ThumbnailLoader(workers=1)
            self.addCleanup(loader.close)
            key = (str(Path(tmp) / "gone.jpg"), 40)
            loader.request(key, fallback=lambda: good)
            done = []
            deadline = time.time() + 5
            while not done and time.time() < deadline:
                done = loader.drain()
                time.sleep(0.01)
            self.assertIsNotNone(done[0][1])

    def test_cache_manager_thumbnail_accessor(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "p.jpg"
            Image.new("RGB", (80, 60), "green").save(source)
            cache = CacheManager(Path(tmp) / ".dsb_cache")
            record = SimpleNamespace(thumbnail_path=Path(tmp) / "missing.jpg", display_source=source, file_path=source)
            rebuilt = cache.thumbnail_for(record)
            self.assertTrue(rebuilt.exists())
            record.thumbnail_path = rebuilt
            self.assertEqual(cache.thumbnail_for(record), rebuilt)


def make_app_fixture(case: unittest.TestCase, count: int, geometry: str = "1320x820"):
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    env = patch.dict(os.environ, {"LOCALAPPDATA": str(root / "appdata")})
    env.start()
    case.addCleanup(env.stop)
    source = root / "source"
    for index in range(count):
        make_record(source / f"IMG_{index:04d}.jpg", index)
    result = ImageScanner(FastMetadata()).scan(source)
    catalog = Catalog(result.catalog_path)
    catalog.update_selections([r.id for r in result.records], pick_status="Unrated", rating=0)
    catalog.close()
    return root, source, result


def open_app(case: unittest.TestCase, source: Path, result, geometry: str = "1320x820"):
    try:
        app = tk_app.ImageManagerApp()
    except tk.TclError as exc:
        case.skipTest(f"Tk display unavailable: {exc}")
    case.addCleanup(close_app, app)
    app.geometry(geometry)
    app.attributes("-alpha", 0)
    app.deiconify()
    app.source_dir = source
    app._catalog_source = source  # as after a real scan, so a rescan of the same folder keeps the history
    app._scan_finished(result.catalog_path)
    pump(app, 0.4)
    return app


def close_app(app):
    """Destroy the app, first stopping a scan a slow machine may still be running.

    destroy() defers closing while a job runs, which would leave a live Tk app
    behind for the following tests.
    """
    try:
        if getattr(app, "_active_job", None) is not None:
            app.cancel_work()
            pump(app, 60, lambda: app._active_job is None)
    except tk.TclError:
        pass
    app.destroy()


def pump(app, seconds=0.3, until=None):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.update()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until is not None else True


class GridAppTests(unittest.TestCase):
    COUNT = 120

    def setUp(self):
        self.root, self.source, self.result = make_app_fixture(self, self.COUNT)
        self.app = open_app(self, self.source, self.result)
        self.app.view_mode.set("grid")
        self.app.apply_view_mode()
        pump(self.app, 0.5)
        self.grid = self.app.grid_view

    def rows(self):
        return list(self.app.tree.get_children())

    def selected_indexes(self):
        rows = self.rows()
        return sorted(rows.index(iid) for iid in self.app.tree.selection())

    def test_grid_is_virtualized_and_loads_visible_thumbnails_only(self):
        self.assertGreater(self.grid.columns, 1)
        drawn = len(self.grid._tiles)
        self.assertGreater(drawn, 0)
        self.assertLess(drawn, self.COUNT // 2)
        self.assertTrue(pump(self.app, 5, lambda: len(self.grid._cache) >= min(drawn, 6)))
        self.assertLess(len(self.grid._cache), self.COUNT)  # thumbnails of tiles never shown are not decoded
        self.assertEqual(self.grid.canvas.winfo_manager(), "pack")
        self.assertEqual(self.app.tree.winfo_manager(), "")

    def test_scrolling_draws_new_tiles_and_drops_old_ones(self):
        first_before = min(self.grid._tiles)
        self.grid.canvas.yview_moveto(0.9)
        pump(self.app, 0.4)
        self.assertGreater(min(self.grid._tiles), first_before)
        self.assertLess(len(self.grid._tiles), self.COUNT // 2)
        self.assertNotIn(0, self.grid._tiles)

    def test_click_shift_ctrl_select_and_stay_shared_with_the_list(self):
        cols = self.grid.columns
        self.app._on_tile_click(2, False, False)
        self.assertEqual(self.selected_indexes(), [2])
        self.app._on_tile_click(5, True, False)
        self.assertEqual(self.selected_indexes(), [2, 3, 4, 5])
        self.app._on_tile_click(9, False, True)
        self.assertEqual(self.selected_indexes(), [2, 3, 4, 5, 9])
        self.app._on_tile_click(3, False, True)
        self.assertEqual(self.selected_indexes(), [2, 4, 5, 9])
        self.assertEqual(self.app.selection_status.get().split(" selected")[0], "4")
        # Switching to the list keeps the very same selection.
        self.app.toggle_view_mode()
        pump(self.app, 0.2)
        self.assertEqual(self.app.view_mode.get(), "list")
        self.assertEqual(self.selected_indexes(), [2, 4, 5, 9])
        self.assertEqual(self.app.tree.winfo_manager(), "pack")
        # ...and a list selection shows up as grid selection.
        self.app.tree.selection_set(self.rows()[7], self.rows()[8])
        self.app.tree.focus(self.rows()[7])
        self.app.on_select()
        self.app.toggle_view_mode()
        pump(self.app, 0.3)
        self.assertEqual(self.selected_indexes(), [7, 8])
        self.assertTrue(cols >= 1)

    def test_click_selection_is_drawn_with_border_and_marker_not_colour_only(self):
        self.app._on_tile_click(1, False, False)
        pump(self.app, 0.2)
        items = self.grid.canvas.find_withtag("t1")
        kinds = [self.grid.canvas.type(i) for i in items]
        widths = [float(self.grid.canvas.itemcget(i, "width")) for i in items if self.grid.canvas.type(i) == "rectangle"]
        self.assertIn(3.0, widths)  # thick selection border
        texts = [self.grid.canvas.itemcget(i, "text") for i in items if self.grid.canvas.type(i) == "text"]
        self.assertIn("●", texts)  # selection marker glyph
        self.assertIn("text", kinds)

    def test_pick_glyph_and_stars_are_drawn_on_tiles(self):
        self.app._on_tile_click(0, False, False)
        self.app.set_pick("Reject", advance=False)
        self.app.set_rating(3, advance=False)
        pump(self.app, 0.3)
        texts = [self.grid.canvas.itemcget(i, "text") for i in self.grid.canvas.find_withtag("t0")
                 if self.grid.canvas.type(i) == "text"]
        self.assertIn("✕", texts)
        self.assertIn("★★★", texts)
        self.assertTrue(any(t.startswith("IMG_0000") for t in texts))

    def test_arrow_keys_move_by_tile_and_by_row(self):
        cols = self.grid.columns
        self.app._on_tile_click(0, False, False)
        ev = lambda state=0: SimpleNamespace(widget=self.grid.canvas, state=state)  # noqa: E731
        self.assertEqual(self.app._on_arrow(ev(), 1), "break")
        self.assertEqual(self.selected_indexes(), [1])
        self.app._on_arrow(ev(), 1, True)
        self.assertEqual(self.selected_indexes(), [1 + cols])
        self.app._on_arrow(ev(), -1, True)
        self.assertEqual(self.selected_indexes(), [1])
        self.app._on_arrow(ev(), -1)
        self.app._on_arrow(ev(), -1)  # clamps at the first tile
        self.assertEqual(self.selected_indexes(), [0])
        # Shift+arrow extends the selection like a list range select.
        self.app._on_arrow(ev(0x1), 1)
        self.app._on_arrow(ev(0x1), 1)
        self.assertEqual(self.selected_indexes(), [0, 1, 2])
        # Text inputs keep their own arrow keys.
        self.assertIsNone(self.app._on_arrow(SimpleNamespace(widget=self.app.file_filter_widget, state=0), 1))

    def test_keyboard_navigation_scrolls_the_focused_tile_into_view(self):
        self.app._on_tile_click(0, False, False)
        for _ in range(40):
            self.app.move_selection(1, vertical=True)
        pump(self.app, 0.3)
        index = self.rows().index(self.app.tree.focus())
        first, stop = self.grid._tiles and (min(self.grid._tiles), max(self.grid._tiles) + 1)
        self.assertTrue(first <= index < stop)
        self.assertGreater(self.grid.scroll_y(), 0)

    def test_marks_shortcuts_undo_and_auto_advance_work_in_grid(self):
        app = self.app
        app.advance_after_mark.set(True)
        app._on_tile_click(0, False, False)
        app.focus_force()
        app.event_generate("<p>")
        pump(app, 0.2)
        self.assertEqual(app.catalog.list_images()[0].pick_status, "Pick")
        self.assertEqual(self.selected_indexes(), [1])  # advanced to the next tile
        app.event_generate("<x>")
        app.event_generate("<KeyPress-4>")
        pump(app, 0.2)
        states = {r.file_path.stem: (r.pick_status, r.rating) for r in app.catalog.list_images()}
        self.assertEqual(states["IMG_0001"][0], "Reject")  # X advanced to tile 2...
        self.assertEqual(states["IMG_0002"], ("Unrated", 4))  # ...so the star rating landed there
        self.assertEqual(self.selected_indexes(), [3])
        app.event_generate("<Control-z>")
        pump(app, 0.2)
        states = {r.file_path.stem: (r.pick_status, r.rating) for r in app.catalog.list_images()}
        self.assertEqual(states["IMG_0002"][1], 0)
        # M/U on a multi-selection apply to every selected tile and do not advance.
        app._on_tile_click(10, False, False)
        app._on_tile_click(12, True, False)
        app.event_generate("<m>")
        pump(app, 0.2)
        picks = [r.pick_status for r in app.catalog.list_images() if r.file_path.stem in ("IMG_0010", "IMG_0011", "IMG_0012")]
        self.assertEqual(picks, ["Maybe"] * 3)
        self.assertEqual(self.selected_indexes(), [10, 11, 12])

    def test_select_all_and_enter_open_actions(self):
        self.app.select_all_visible()
        pump(self.app, 0.2)
        self.assertEqual(len(self.app.tree.selection()), self.COUNT)
        with patch.object(self.app, "open_fullscreen_viewer") as viewer:
            self.app._on_tile_activate(3)
            viewer.assert_called_once()
            viewer.reset_mock()
            self.grid.canvas.focus_force()
            self.app.update()
            self.grid.canvas.event_generate("<Return>")
            self.app.update()
            viewer.assert_called_once()
        self.assertEqual(self.selected_indexes(), [3])

    def test_g_toggles_view_and_keeps_scroll_position(self):
        self.grid.canvas.yview_moveto(0.5)
        pump(self.app, 0.3)
        top = self.grid.top_index()
        self.assertGreater(top, 0)
        self.app.focus_force()
        self.app.event_generate("<g>")
        pump(self.app, 0.3)
        self.assertEqual(self.app.view_mode.get(), "list")
        rows = len(self.rows())
        listed_top = round(self.app.tree.yview()[0] * rows)
        self.assertLess(abs(listed_top - top), 4)
        self.app.event_generate("<G>")
        pump(self.app, 0.3)
        self.assertEqual(self.app.view_mode.get(), "grid")
        self.assertLess(abs(self.grid.top_index() - (top // self.grid.columns) * self.grid.columns), 2 * self.grid.columns)

    def test_streaming_rows_add_tiles_progressively(self):
        app = self.app
        with patch.object(tk_app, "ImageScanner", return_value=ImageScanner(FastMetadata())):
            app.scan_folder()
            # Rows land before the scan ends; the grid follows the row list.
            self.assertTrue(pump(app, 60, lambda: app._active_job is None), "scan did not finish")
        pump(app, 0.4)
        self.assertEqual(len(app.records), self.COUNT)
        self.assertEqual(self.grid._n, self.COUNT)
        self.assertGreater(len(self.grid._tiles), 0)

    def test_tile_size_changes_tile_pixels_and_persists(self):
        before = self.grid.metrics.tile
        self.app.grid_size.set("small")
        self.app.apply_grid_size()
        pump(self.app, 0.3)
        self.assertLess(self.grid.metrics.tile, before)
        self.assertEqual(get_section(tk_app.SETTINGS_SECTION)["grid_size"], "small")
        self.app.grid_size.set("large")
        self.app.apply_grid_size()
        self.assertGreater(self.grid.metrics.tile, before)

    def test_empty_state_overlay_covers_the_grid_when_filters_hide_everything(self):
        self.app.pick_filter.set("Reject")
        self.app.refresh_records()
        pump(self.app, 0.3)
        self.assertEqual(self.app.records, [])
        self.assertEqual(self.app.empty_overlay.winfo_manager(), "place")
        self.assertIs(self.app.empty_overlay.place_info()["in"], self.grid)


class UndoIdentityTests(unittest.TestCase):
    def _rescan(self, app):
        with patch.object(tk_app, "ImageScanner", return_value=ImageScanner(FastMetadata())):
            app.scan_folder()
            pump(app, 15, lambda: app._active_job is None)
        pump(app, 0.3)

    def _states(self, app):
        return {r.file_path.name: (r.pick_status, r.rating) for r in app.catalog.list_images()}

    def test_undo_after_rescan_never_touches_a_different_image(self):
        root, source, result = make_app_fixture(self, 4)
        app = open_app(self, source, result)
        app._select_only(app.tree.get_children()[0])
        app.set_pick("Reject", advance=False)
        self.assertEqual(self._states(app)["IMG_0000.jpg"][0], "Reject")
        (source / "IMG_0000.jpg").unlink()
        make_record(source / "ZZZ_new.jpg", 99)
        self._rescan(app)
        before = self._states(app)
        self.assertNotIn("IMG_0000.jpg", before)
        app.undo()
        pump(app, 0.2)
        self.assertEqual(self._states(app), before)  # the stale entry restored nothing, anywhere
        self.assertIn("Nothing to undo", app.status.get())

    def test_undo_restores_the_whole_shot_when_a_raw_partner_appeared(self):
        root, source, result = make_app_fixture(self, 3)
        app = open_app(self, source, result)
        app._select_only(app.tree.get_children()[1])
        app.set_pick("Pick", advance=False)
        app.set_rating(3, advance=False)
        (source / "IMG_0001.CR3").write_bytes((source / "IMG_0001.jpg").read_bytes())
        self._rescan(app)
        states = self._states(app)
        self.assertEqual(states["IMG_0001.CR3"], ("Pick", 3))  # the partner joined the shot
        app.undo()  # rating
        app.undo()  # pick
        pump(app, 0.2)
        states = self._states(app)
        self.assertEqual(states["IMG_0001.jpg"], ("Unrated", 0))
        self.assertEqual(states["IMG_0001.CR3"], ("Unrated", 0))
        app.redo()
        pump(app, 0.2)
        states = self._states(app)
        self.assertEqual(states["IMG_0001.jpg"], states["IMG_0001.CR3"])


class ViewPersistenceTests(unittest.TestCase):
    def test_view_mode_and_size_survive_a_restart(self):
        root, source, result = make_app_fixture(self, 6)
        first = open_app(self, source, result)
        self.assertEqual(first.view_mode.get(), "list")  # default
        self.assertEqual(first.tree.winfo_manager(), "pack")
        first.view_mode.set("grid")
        first.apply_view_mode()
        first.grid_size.set("large")
        first.apply_grid_size()
        self.assertEqual(get_section(tk_app.SETTINGS_SECTION)["view_mode"], "grid")
        first.destroy()
        second = open_app(self, source, result)
        self.assertEqual(second.view_mode.get(), "grid")
        self.assertEqual(second.grid_size.get(), "large")
        self.assertEqual(second.grid_view.winfo_manager(), "pack")
        second.toggle_view_mode()
        self.assertEqual(get_section(tk_app.SETTINGS_SECTION)["view_mode"], "list")

    def test_garbage_settings_fall_back_to_list_and_medium(self):
        root, source, result = make_app_fixture(self, 3)
        from ndex_common.settings import update_section

        update_section(tk_app.SETTINGS_SECTION, {"view_mode": "tiles", "grid_size": 12})
        app = open_app(self, source, result)
        self.assertEqual((app.view_mode.get(), app.grid_size.get()), ("list", "medium"))

    def test_view_menu_offers_list_grid_and_sizes(self):
        root, source, result = make_app_fixture(self, 3)
        app = open_app(self, source, result)
        menubar = app.nametowidget(app.cget("menu"))
        view = None
        labels = []
        for index in range(menubar.index("end") + 1):
            if menubar.type(index) == "cascade" and menubar.entrycget(index, "label") == "View":
                view = menubar.nametowidget(menubar.entrycget(index, "menu"))
        for index in range(view.index("end") + 1):
            if view.type(index) != "separator":
                labels.append(view.entrycget(index, "label"))
        self.assertIn("List", labels)
        self.assertIn("Grid", labels)
        self.assertIn("Thumbnail Size", labels)


class CompactLayoutTests(unittest.TestCase):
    def test_minimum_window_has_one_toolbar_row_and_at_least_ten_list_rows(self):
        root, source, result = make_app_fixture(self, 40)
        app = open_app(self, source, result, "1040x680")
        app.geometry("1040x680")
        pump(app, 0.8)
        self.assertEqual(app.winfo_width(), 1040)
        self.assertFalse(app._actions_stacked, "toolbar wrapped to a second row")
        # Everything in the toolbar sits on one line.
        tops = {w.winfo_rooty() for w in (app.choose_button, app.mark_buttons["Pick"], app.export_button,
                                          app.send_selector_button, app.send_frame_button)}
        self.assertEqual(len(tops), 1)
        row_height = int(tk_app.ttk.Style(app).lookup("Treeview", "rowheight") or 20)
        self.assertGreaterEqual(app.tree.winfo_height() // row_height, 10)
        self.assertGreater(app.preview_label.winfo_height(), 50)
        self.assertTrue(app.preview_label.winfo_ismapped())

    def test_default_window_keeps_one_toolbar_row(self):
        root, source, result = make_app_fixture(self, 10)
        app = open_app(self, source, result, "1320x820")
        pump(app, 0.5)
        self.assertFalse(app._actions_stacked)

    def test_toolbar_labels_are_short_and_tooltips_carry_the_description(self):
        root, source, result = make_app_fixture(self, 3)
        app = open_app(self, source, result)
        self.assertEqual(app.export_button.cget("text"), "Export…")
        self.assertEqual(app.send_selector_button.cget("text"), "→ Auto Selector")
        self.assertEqual(app.send_frame_button.cget("text"), "→ Frame")
        self.assertEqual([app.mark_buttons[k].cget("text") for k in ("Pick", "Maybe", "Reject", "Unrated")],
                         ["Pick", "Maybe", "Reject", "Clear"])
        self.assertIn("Auto Selector", app._hint("selector"))


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(i18n.init, "test", "en")

    def _override(self, root: Path, entries: dict) -> None:
        folder = root / "NDEX" / "locales"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ko.json").write_text(json.dumps({"__meta__": {"name": "한국어", "code": "ko"}, **entries},
                                                   ensure_ascii=False), encoding="utf-8")

    def test_main_initialises_i18n_before_any_ui(self):
        from dsb_image_manager import main as main_module

        order = []
        with patch.object(main_module.i18n, "init", side_effect=lambda *a, **k: order.append(("init", a))), \
                patch.object(main_module, "install_crash_logging", side_effect=lambda *a: order.append(("crash", a))), \
                patch.object(main_module, "run_app", side_effect=lambda **k: order.append(("ui", k))), \
                patch.object(sys, "argv", ["image_manager"]):
            self.assertEqual(main_module.main(), 0)
        self.assertEqual(order[0], ("init", ("image_manager",)))
        self.assertEqual(order[-1][0], "ui")

    def test_display_labels_translate_but_internal_keys_never_change(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        self._override(root, {"All files": "모든 파일", "Pick": "선택", "Pairs (RAW+JPG)": "쌍"})
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root)}):
            i18n.init("image_manager", "ko")
            files = tk_app.file_filter_options()
            self.assertEqual(files[0], ("all", "모든 파일"))
            self.assertEqual(tk_app.value_for(files, "쌍"), "paired")
            self.assertEqual(tk_app.label_for(files, "paired"), "쌍")
            self.assertEqual(tk_app.pick_label("Pick"), "선택")
            self.assertEqual(tk_app.pick_label("Reject"), "Reject")  # untranslated -> English fallback
            self.assertEqual([k for k, _ in tk_app.pick_filter_options()], ["all", "Unrated", "Pick", "Maybe", "Reject"])

    def test_counts_and_sentences_use_placeholders_and_plural_forms(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        self._override(root, {
            "Ready. {files} ({shots})": "준비됨. {files} ({shots})",
            "__plural__": {"{count} file": ["{count}개 파일"], "{count} shot": ["{count}컷"]},
        })
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root)}):
            i18n.init("image_manager", "ko")
            self.assertEqual(tk_app.ready_status_text(60, 36), "준비됨. 60개 파일 (36컷)")
        i18n.init("image_manager", "en")
        self.assertEqual(tk_app.ready_status_text(1, 1), "Ready. 1 file (1 shot)")
        self.assertEqual(tk_app.ready_status_text(60, 36), "Ready. 60 files (36 shots)")

    def test_ui_is_built_from_translated_text(self):
        root, source, result = make_app_fixture(self, 4)
        override = Path(os.environ["LOCALAPPDATA"])
        self._override(override, {
            "Pick": "선택", "Reject": "제외", "Export…": "내보내기…", "File": "파일", "View": "보기", "Grid": "격자",
        })
        i18n.init("image_manager", "ko")
        app = open_app(self, source, result)
        self.assertEqual(app.mark_buttons["Pick"].cget("text"), "선택")
        self.assertEqual(app.mark_buttons["Reject"].cget("text"), "제외")
        self.assertEqual(app.export_button.cget("text"), "내보내기…")
        self.assertEqual(app.tree.heading("name")["text"], "파일")
        menubar = app.nametowidget(app.cget("menu"))
        labels = [menubar.entrycget(i, "label") for i in range(menubar.index("end") + 1)
                  if menubar.type(i) == "cascade"]
        self.assertIn("\ubcf4\uae30", labels)
        # Behaviour is driven by internal keys, not the translated text.
        app.pick_filter_widget.set(tk_app.label_for(tk_app.pick_filter_options(), "Pick"))
        app.pick_filter_widget.current(2)
        app.pick_filter_widget.event_generate("<<ComboboxSelected>>")
        app.update()
        self.assertEqual(app.pick_filter.get(), "Pick")

    def test_ko_json_contains_every_image_manager_string(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
        try:
            import i18n_extract
        finally:
            sys.path.pop(0)
        repo = Path(__file__).resolve().parents[2]
        messages, plurals = i18n_extract.extract_tree([repo / "dsb_image_manager"])
        data = json.loads((repo / "ndex_common" / "locales" / "ko.json").read_text(encoding="utf-8-sig"))
        self.assertFalse(sorted(m for m in messages if m not in data)[:5])
        self.assertFalse(sorted(p for p in plurals if p not in data.get("__plural__", {}))[:5])
        self.assertGreater(len(messages), 150)


if __name__ == "__main__":
    unittest.main()
