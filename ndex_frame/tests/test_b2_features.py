from __future__ import annotations

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QToolButton

from ndex_frame.core.models import AspectRatio
from ndex_frame.services.cache import PreviewCache
from ndex_frame.services.importer import analyze_source
from ndex_frame.services.presets import PresetStore
from ndex_frame.services.thumbnails import ThumbnailCache
from ndex_frame.ui.main_window import MainWindow
from ndex_frame.ui.presets_manager import FRAME, OUTPUT, PresetNameError, PresetsManagerDialog, frame_summary, output_summary
from ndex_frame.ui.thumbnail_loader import ThumbnailLoader
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState


def _wait_until(predicate, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QTest.qWait(20)
        if predicate():
            return True
    return predicate()


class ThumbnailCacheTests(unittest.TestCase):
    def test_creates_small_cached_png_and_rekeys_on_change(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            photo = root / "a.jpg"
            Image.new("RGB", (3000, 2000), (200, 30, 30)).save(photo)
            cache = ThumbnailCache(root / "thumbs")
            first = cache.get_or_create(photo, 96)
            with Image.open(first) as image:
                self.assertEqual(max(image.size), 96)
            self.assertEqual(cache.get_or_create(photo, 96), first)
            self.assertEqual(list((root / "thumbs").glob("*.tmp")), [])
            time.sleep(0.02)
            Image.new("RGB", (3000, 2000), (0, 0, 255)).save(photo)
            self.assertNotEqual(cache.get_or_create(photo, 96), first)


class ThumbnailWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        self.store = PresetStore(self.root / "data")
        self.state = WorkspaceState(
            working_frame=self.store.default_frame(), output_profile=self.store.default_output()
        )
        from ndex_frame.services.cache import PreviewCache

        self.controller = WorkspaceController(
            self.state,
            preview_cache=PreviewCache(self.root / "cache"),
            settings_writer=lambda _s, _v: None,
        )

    def _photos(self, count: int):
        paths = []
        for index in range(count):
            path = self.root / f"P{index:03d}.jpg"
            Image.new("RGB", (400, 300), (index % 255, 90, 160)).save(path)
            paths.append(path)
        return [analyze_source(path) for path in paths]

    def test_only_visible_rows_are_loaded_and_placeholder_until_ready(self) -> None:
        window = MainWindow(self.controller, preset_store=self.store)
        self.addCleanup(window.teardown)
        window.resize(1180, 760)
        window.show()
        self.state.replace_sources(self._photos(300))
        window.refresh_thumbnails()
        first = self.state.sources[0].path
        self.assertIsNone(window.thumbnail_loader.pixmap_for(first))
        self.assertFalse(window._item_by_path[first].icon().isNull())  # placeholder
        wanted = window.visible_thumbnail_paths()
        self.assertLess(len(wanted), 60)
        self.assertEqual(wanted[0], first)
        window.load_visible_thumbnails()
        self.assertTrue(_wait_until(lambda: window.thumbnail_loader.pixmap_for(first) is not None))
        last = self.state.sources[-1].path
        self.assertIsNone(window.thumbnail_loader.pixmap_for(last))
        # Scrolling to the end loads the tail and keeps the text/badge format.
        window.thumbnail_view.scrollToBottom()
        window.load_visible_thumbnails()
        self.assertTrue(_wait_until(lambda: window.thumbnail_loader.pixmap_for(last) is not None))
        self.assertIn("Default", window._item_by_path[first].text())

    def test_keyboard_navigation_still_steps_through_photos(self) -> None:
        window = MainWindow(self.controller, preset_store=self.store)
        self.addCleanup(window.teardown)
        self.state.replace_sources(self._photos(3))
        window.refresh_thumbnails()
        window.thumbnail_view.setCurrentRow(0)
        self.assertTrue(window.step_selection(1))
        self.assertEqual(window.thumbnail_view.currentRow(), 1)

    def test_loader_drops_requests_that_scrolled_away(self) -> None:
        photos = self._photos(6)
        loader = ThumbnailLoader(ThumbnailCache(self.root / "t"), workers=1)
        self.addCleanup(loader.shutdown)
        paths = [photo.path for photo in photos]
        loader.request(paths)
        loader.request(paths[:1])  # the rest are no longer wanted
        self.assertEqual(loader.wanted, {paths[0]})
        self.assertTrue(_wait_until(lambda: loader.pixmap_for(paths[0]) is not None))

    def test_toolbar_fits_at_minimum_width(self) -> None:
        window = MainWindow(self.controller, preset_store=self.store)
        self.addCleanup(window.teardown)
        window.show()
        window.resize(1, 1)
        QTest.qWait(50)
        self.assertGreaterEqual(window.width(), window.toolbar.sizeHint().width())
        extension = [b for b in window.findChildren(QToolButton) if b.objectName() == "qt_toolbar_ext_button"]
        self.assertFalse(any(button.isVisible() for button in extension))

    def test_edited_frame_is_marked_in_words(self) -> None:
        window = MainWindow(self.controller, preset_store=self.store)
        self.addCleanup(window.teardown)
        name = window.frame_preset_combo.currentData().name
        window.background_preset_buttons[3].click()
        self.assertEqual(window.frame_preset_combo.currentText(), f"{name} (edited)")


class PresetsManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.store = PresetStore(Path(self._dir.name), lambda _s, d: dict(d), lambda _s, _v: None)
        self.used: list = []
        self.dialog = PresetsManagerDialog(
            self.store,
            current_frame=self.store.default_frame(),
            current_output=self.store.default_output(),
            on_use_frame=lambda preset: self.used.append(("frame", preset.id)),
            on_use_output=lambda preset: self.used.append(("output", preset.id)),
        )
        self.addCleanup(self.dialog.close)

    def test_builtins_are_read_only_but_duplicable(self) -> None:
        for column in (self.dialog.frames, self.dialog.outputs):
            self.assertTrue(column.list.currentItem() is not None)
            self.assertTrue(column.duplicate_button.isEnabled())
            for button in (column.edit_button, column.rename_button, column.delete_button):
                self.assertFalse(button.isEnabled())

    def test_frame_round_trip_create_rename_duplicate_delete(self) -> None:
        created = self.dialog.create(FRAME, "Wedding 4:5")
        self.assertTrue(created.id.startswith("custom."))
        self.assertIn(created.id, [p.id for p in self.store.list_frames()])
        self.assertEqual(self.dialog.frames.selected_id(), created.id)
        self.assertTrue(self.dialog.frames.rename_button.isEnabled())
        self.dialog.rename(FRAME, created.id, "Wedding")
        self.assertEqual(self.dialog.preset(FRAME, created.id).name, "Wedding")
        copy = self.dialog.duplicate(FRAME, created.id)
        self.assertEqual(copy.name, "Wedding copy")
        self.assertNotEqual(copy.id, created.id)
        self.dialog.delete(FRAME, created.id)
        self.dialog.delete(FRAME, copy.id)
        self.assertFalse([p for p in self.store.list_frames() if not p.builtin])

    def test_output_round_trip_and_store_survives_reload(self) -> None:
        copy = self.dialog.duplicate(OUTPUT, self.store.default_output().id)
        self.dialog.rename(OUTPUT, copy.id, "Web small")
        reloaded = PresetStore(Path(self._dir.name), lambda _s, d: dict(d), lambda _s, _v: None)
        self.assertEqual(
            {p.name for p in reloaded.list_outputs() if not p.builtin}, {"Web small"}
        )
        self.dialog.delete(OUTPUT, copy.id)
        self.assertEqual([p for p in reloaded.list_outputs() if not p.builtin], [])

    def test_name_rules_and_builtin_protection(self) -> None:
        with self.assertRaises(PresetNameError):
            self.dialog.create(FRAME, "   ")
        with self.assertRaises(PresetNameError):
            self.dialog.create(FRAME, self.store.default_frame().name)
        with self.assertRaises(ValueError):
            self.dialog.delete(FRAME, self.store.default_frame().id)
        with self.assertRaises(ValueError):
            self.dialog.rename(FRAME, self.store.default_frame().id, "Other")

    def test_summaries_describe_the_selection(self) -> None:
        frame = self.store.default_frame()
        text = frame_summary(frame)
        self.assertIn("3:4", text)
        self.assertIn(frame.background, text)
        self.assertIn("Border", text)
        self.assertEqual(self.dialog.frames.summary.text(), text)
        output = output_summary(self.store.default_output())
        for word in ("Size", "Format", "quality", "Metadata"):
            self.assertIn(word, output)
        self.assertEqual(self.dialog.outputs.summary.text(), output)

    def test_use_sets_current_and_buttons_prompt(self) -> None:
        created = self.dialog.create(FRAME, "Mine")
        self.dialog.use(FRAME)
        self.assertEqual(self.used, [("frame", created.id)])
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.dialog.frames.delete_button.click()
        self.assertNotIn(created.id, [p.id for p in self.store.list_frames()])
        with patch("ndex_frame.ui.presets_manager.QInputDialog.getText", return_value=("Fresh", True)):
            self.dialog.frames.new_button.click()
        self.assertIn("Fresh", [p.name for p in self.store.list_frames()])


class MainWindowPresetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_manage_presets_opens_manager_and_use_updates_window(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = PresetStore(Path(folder))
            state = WorkspaceState(working_frame=store.default_frame(), output_profile=store.default_output())
            controller = WorkspaceController(state, settings_writer=lambda _s, _v: None)
            window = MainWindow(controller, preset_store=store)
            window.set_interactive_dialogs(False)
            self.addCleanup(window.teardown)
            window.manage_presets_button.click()
            dialog = window._last_presets_dialog
            self.assertIsInstance(dialog, PresetsManagerDialog)
            created = dialog.create(FRAME, "Square")
            dialog.use(FRAME)
            self.assertEqual(state.working_frame.id, created.id)
            self.assertEqual(window.frame_preset_combo.currentText(), "Square")
            dialog.delete(FRAME, created.id)
            window._reload_preset_combos()
            self.assertEqual(state.working_frame.id, store.default_frame().id)

    def _window(self, folder: str):
        store = PresetStore(Path(folder))
        state = WorkspaceState(working_frame=store.default_frame(), output_profile=store.default_output())
        controller = WorkspaceController(
            state, preview_cache=PreviewCache(Path(folder) / "cache"), settings_writer=lambda _s, _v: None
        )
        window = MainWindow(controller, preset_store=store)
        window.set_interactive_dialogs(False)
        self.addCleanup(window.teardown)
        return window, store, state, controller

    def test_new_preset_in_manager_captures_current_working_edits(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            window, store, state, controller = self._window(folder)
            controller.update_working_frame(ratio=AspectRatio(7, 5), background="#123456", photo_scale=0.8)
            window.manage_presets_button.click()
            created = window._last_presets_dialog.create(FRAME, "From edits")
            self.assertEqual((created.ratio.width, created.ratio.height), (7, 5))
            self.assertEqual(created.background, "#123456")
            self.assertAlmostEqual(created.photo_scale, 0.8)

    def test_use_as_current_survives_manager_closing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            window, store, state, controller = self._window(folder)
            base = state.working_frame
            controller.update_working_frame(background="#123456")
            self.assertNotEqual(state.working_frame.background, base.background)

            def use_same_preset(dialog) -> int:
                dialog.select(FRAME, base.id)
                dialog.use(FRAME)
                return 0

            window.set_interactive_dialogs(True)
            with patch.object(PresetsManagerDialog, "exec", use_same_preset):
                window._manage_presets()
            self.assertEqual(state.working_frame.background, base.background)
            self.assertEqual(state.working_frame.id, base.id)

    def test_closing_manager_without_choosing_keeps_unsaved_edits(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            window, store, state, controller = self._window(folder)
            controller.update_working_frame(background="#123456")
            window.set_interactive_dialogs(True)
            with patch.object(PresetsManagerDialog, "exec", lambda dialog: 0):
                window._manage_presets()
            self.assertEqual(state.working_frame.background, "#123456")

    def test_teardown_leaves_no_worker_running(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            window, store, state, controller = self._window(folder)
            paths = []
            for index in range(8):
                path = Path(folder) / f"P{index}.jpg"
                Image.new("RGB", (400, 300), (index, 90, 160)).save(path)
                paths.append(path)
            state.replace_sources([analyze_source(path) for path in paths])
            window.refresh_thumbnails()
            window.load_visible_thumbnails()
            self.assertTrue(window.teardown())
            self.assertEqual(controller.thread_pool.activeThreadCount(), 0)
            self.assertEqual(window.thumbnail_loader._pool.activeThreadCount(), 0)
            self.assertTrue(window.thumbnail_loader.stopped)


class LocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_window_and_messages_use_translations(self) -> None:
        from ndex_common import i18n
        from ndex_frame.core.messages import ImportSummary, import_status_text

        table = {
            "Open Files": "파일 열기",
            "{name} (edited)": "{name} (수정됨)",
        }
        plurals = {"Opened {count} photo{source}": ["{count}장 열었습니다{source}"]}
        with patch.dict(i18n._messages, table), patch.dict(i18n._plurals, plurals):
            with tempfile.TemporaryDirectory() as folder:
                store = PresetStore(Path(folder))
                state = WorkspaceState(working_frame=store.default_frame(), output_profile=store.default_output())
                controller = WorkspaceController(state, settings_writer=lambda _s, _v: None)
                window = MainWindow(controller, preset_store=store)
                self.addCleanup(window.teardown)
                self.assertEqual(window.open_files_button.text(), "파일 열기")
                window.background_preset_buttons[3].click()
                self.assertTrue(window.frame_preset_combo.currentText().endswith("(수정됨)"))
            self.assertEqual(import_status_text(ImportSummary(opened=2)), "2장 열었습니다")
        self.assertEqual(import_status_text(ImportSummary(opened=2)), "Opened 2 photos")

    def test_frame_keys_are_in_the_korean_catalog(self) -> None:
        import json
        from ndex_common import i18n

        data = json.loads((i18n.bundled_locales_dir() / "ko.json").read_text(encoding="utf-8"))
        for key in ("Manage Presets", "Retry Failed", "{count} failed", "Use as Current Frame"):
            self.assertIn(key, data)


if __name__ == "__main__":
    unittest.main()
