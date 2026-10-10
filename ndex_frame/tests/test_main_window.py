from __future__ import annotations

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontDatabase, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog

from ndex_frame.core.geometry import build_render_plan, project_render_plan
from ndex_frame.core.models import AspectRatio, FramePreset, MetadataPolicy, OutputProfile, OutputSizing, SourceItem
from ndex_frame.main import build_parser
from ndex_frame.services.export_job import ExportProgress, ExportResult
from ndex_frame.ui.main_window import MainWindow
from ndex_frame.ui.preview_widget import PreviewWidget
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        # Windows' offscreen platform does not discover system fonts itself.
        if os.name == "nt":
            font_directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
                QFontDatabase.addApplicationFont(str(font_directory / filename))

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

    def test_composes_preview_first_single_window(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        self.assertEqual(window.windowTitle(), "NDEX Frame")
        self.assertIsNotNone(window.thumbnail_view)
        self.assertIsNotNone(window.preview_widget)
        self.assertIsNotNone(window.frame_panel)
        self.assertEqual(window.export_all_button.text(), "Export All")
        self.assertEqual(window.scale_slider.minimum(), 10)
        self.assertEqual(window.scale_slider.maximum(), 100)
        self.assertEqual(window.x_spin.minimum(), -1.0)
        self.assertEqual(window.x_spin.maximum(), 1.0)
        self.assertEqual(window.frame_preset_combo.accessibleName(), "Frame Preset")
        self.assertEqual(window.output_profile_combo.accessibleName(), "Output Profile")
        self.assertEqual(window.thumbnail_view.accessibleName(), "Source Images")
        self.assertEqual(window.scale_slider.accessibleName(), "Photo Size")
        self.assertEqual(window.ratio_width_spin.value(), 3)
        self.assertEqual(window.ratio_height_spin.value(), 4)
        self.assertEqual(
            [button.accessibleName() for button in window.background_preset_buttons],
            ["White", "Bright Gray", "Medium Gray", "Black"],
        )
        self.assertEqual(window.custom_background_button.text(), "Custom…")
        self.assertGreaterEqual(window.frame_panel.minimumWidth(), 270)
        self.assertGreaterEqual(window.custom_background_button.minimumWidth(), 72)
        from ndex_frame.ui.framing_widgets import ColorSwatchButton

        for swatch in window.background_preset_buttons:
            self.assertEqual(swatch.objectName(), "colorSwatch")
            self.assertIsInstance(swatch, ColorSwatchButton)
        self.assertIsNone(getattr(window, "background_edit", None))
        self.assertEqual(
            [button.text() for button in window.ratio_preset_buttons],
            ["3:4", "4:5", "1:1"],
        )
        self.assertEqual(
            [button.text() for button in window.photo_size_preset_buttons],
            ["80%", "90%", "95%"],
        )
        self.assertTrue(window.export_progress_bar.isHidden())
        self.assertEqual(window.export_progress_bar.accessibleName(), "Export progress")

    def test_export_progress_bar_tracks_files_and_hides_when_finished(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window._export_progress(ExportProgress(1, 3, Path("one.jpg"), "started"))
        self.assertFalse(window.export_progress_bar.isHidden())
        self.assertEqual(window.export_progress_bar.maximum(), 3)
        self.assertEqual(window.export_progress_bar.value(), 1)
        self.assertEqual(window.export_progress_bar.format(), "%v / %m")
        self.assertEqual(window.export_progress_bar.toolTip(), "one.jpg")
        window._export_progress(ExportProgress(2, 3, Path("two.jpg"), "exported"))
        self.assertEqual(window.export_progress_bar.value(), 2)
        window.set_interactive_dialogs(False)
        window._export_finished(ExportResult(2, 0, 0, False, ()))
        self.assertTrue(window.export_progress_bar.isHidden())

    def test_long_output_path_does_not_expand_window_or_hide_export_actions(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.show()
        window.resize(960, 640)
        self.app.processEvents()
        original_minimum = window.minimumSizeHint().width()
        path = Path("C:/Photos") / "/".join(["Client approved autumn photographs"] * 12) / "Final Export"
        self.state.output_directory = path
        window.sync_output_folder_label()
        self.app.processEvents()

        self.assertEqual(window.width(), 960)
        self.assertEqual(window.minimumSizeHint().width(), original_minimum)
        self.assertEqual(window.output_folder_label.text(), str(path))
        self.assertEqual(window.output_folder_label.toolTip(), str(path))
        self.assertEqual(window.output_folder_label.accessibleDescription(), str(path))
        for button in (window.output_folder_button, window.export_selected_button, window.export_all_button):
            position = button.mapTo(window, QPoint())
            self.assertTrue(window.rect().contains(position))
            self.assertTrue(window.rect().contains(position + button.rect().bottomRight()))

    def test_short_window_keeps_cancel_visible_and_settings_scrollable(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.show()
        window.resize(900, 600)
        with patch.object(self.controller, "_export_thread", object()):
            window._busy_changed(True)
            filename = "approved-autumn-photo-" * 12 + ".jpg"
            window._export_progress(ExportProgress(1, 3, Path(filename), "started"))
            self.app.processEvents()
            self.assertEqual(window.size().toTuple(), (900, 600))
            for widget in (window.cancel_button, window.export_progress_bar, window.export_all_button):
                position = widget.mapTo(window, QPoint())
                self.assertTrue(widget.isVisible())
                self.assertTrue(window.rect().contains(position + widget.rect().bottomRight()))
            self.assertGreater(window.frame_scroll.verticalScrollBar().maximum(), 0)
            window.frame_scroll.ensureWidgetVisible(window.save_frame_button)
            self.app.processEvents()
            position = window.save_frame_button.mapTo(window.frame_scroll.viewport(), QPoint())
            self.assertTrue(window.frame_scroll.viewport().rect().contains(position))
            self.assertTrue(window.frame_scroll.viewport().rect().contains(
                position + window.save_frame_button.rect().bottomRight()
            ))
        window._busy_changed(False)

    def test_selected_controls_require_a_photo_and_reset_only_that_photo(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        self.assertFalse(window.scale_spin.isEnabled())
        self.assertFalse(window.reset_override_button.isEnabled())
        self.assertTrue(window.ratio_width_spin.isEnabled())

        first = SourceItem(Path("first.jpg"), 3000, 4000, True)
        second = SourceItem(Path("second.jpg"), 3000, 4000, True)
        self.state.replace_sources([first, second])
        window._refresh_sources()
        self.assertTrue(window.scale_spin.isEnabled())
        window.photo_size_preset_buttons[0].click()
        self.state.select(second.path)
        window._sync_controls()
        window.photo_size_preset_buttons[1].click()
        window.ratio_preset_buttons[2].click()
        window.background_preset_buttons[3].click()
        self.assertEqual(self.state.working_frame.ratio, AspectRatio(1, 1))
        self.assertEqual(self.state.working_frame.background, "#000000")
        self.assertEqual(self.state.effective_framing(first.path)[0], 0.8)
        self.assertEqual(self.state.effective_framing(second.path)[0], 0.9)
        self.assertTrue(window.reset_override_button.isEnabled())
        window.reset_override_button.click()
        self.assertEqual(self.state.effective_framing(first.path)[0], 0.8)
        self.assertEqual(self.state.effective_framing(second.path)[0], 1.0)
        self.assertFalse(window.reset_override_button.isEnabled())

    def test_ratio_and_background_presets_update_working_frame(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.ratio_preset_buttons[1].click()
        self.assertEqual(
            (self.state.working_frame.ratio.width, self.state.working_frame.ratio.height),
            (4, 5),
        )
        window.ratio_width_spin.setValue(3)
        window.ratio_height_spin.setValue(4)
        self.assertEqual(
            (self.state.working_frame.ratio.width, self.state.working_frame.ratio.height),
            (3, 4),
        )
        window.background_preset_buttons[3].click()
        self.assertEqual(self.state.working_frame.background, "#000000")
        window._apply_background("#AABBCC")
        self.assertEqual(self.state.working_frame.background, "#AABBCC")

    def test_apply_all_copies_selected_size_ratio_and_color_to_every_photo(self) -> None:
        first = SourceItem(Path("first.jpg"), 3000, 4000, True)
        second = SourceItem(Path("second.jpg"), 5000, 7000, True)
        self.state.replace_sources([first, second])
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.ratio_preset_buttons[2].click()
        window.background_preset_buttons[1].click()
        window.photo_size_preset_buttons[0].click()
        self.assertTrue(self.state.is_modified(first.path))
        self.assertFalse(self.state.is_modified(second.path))
        window.apply_all_button.click()
        self.assertEqual(self.state.working_frame.ratio.width, 1)
        self.assertEqual(self.state.working_frame.ratio.height, 1)
        self.assertEqual(self.state.working_frame.background, "#D0D0D0")
        self.assertEqual(self.state.working_frame.photo_scale, 0.80)
        self.assertEqual(self.state.overrides, {})
        self.assertEqual(self.state.effective_framing(second.path), (0.80, 0.0, 0.0))

    def test_photo_size_preset_sets_selected_scale(self) -> None:
        source = SourceItem(Path("master.jpg"), 3000, 4000, True)
        self.state.replace_sources([source])
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.photo_size_preset_buttons[0].click()
        self.assertEqual(self.state.effective_framing(source.path)[0], 0.80)
        self.assertEqual(window.scale_spin.value(), 80)
        window.photo_size_preset_buttons[2].click()
        self.assertEqual(self.state.effective_framing(source.path)[0], 0.95)

    def test_selecting_output_folder_enables_export_after_import(self) -> None:
        self.state.replace_sources([SourceItem(Path("master.jpg"), 3000, 4000, True)])
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        self.assertFalse(window.export_all_button.isEnabled())
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(QFileDialog, "getExistingDirectory", return_value=directory):
                window._choose_output_folder()
            self.assertTrue(window.export_all_button.isEnabled())
            self.assertTrue(window.export_selected_button.isEnabled())

    def test_opening_files_clears_a_previous_handoff(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.handoff_path = Path("select-handoff.json")
        with tempfile.TemporaryDirectory() as directory:
            master = Path(directory) / "master.jpg"
            master.write_bytes(b"jpg")
            with patch.object(QFileDialog, "getOpenFileNames", return_value=([str(master)], "")):
                window._choose_files()
        self.assertIsNone(window.handoff_path)

    def test_opening_a_folder_clears_a_previous_handoff(self) -> None:
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        window.handoff_path = Path("select-handoff.json")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(QFileDialog, "getExistingDirectory", return_value=directory):
                window._choose_folder()
        self.assertIsNone(window.handoff_path)

    def test_preview_projects_exact_export_plan(self) -> None:
        widget = PreviewWidget()
        widget.resize(540, 720)
        plan = build_render_plan((6000, 4000), (1080, 1440), 0.9, 0.25, -0.5)
        widget.set_preview(QPixmap.fromImage(QImage(60, 40, QImage.Format.Format_RGB32)), plan)
        actual = widget.projected_plan()
        expected = project_render_plan(plan, (540, 720))
        self.assertEqual(actual, expected)

    def test_controller_builds_preview_from_full_source_export_plan(self) -> None:
        source = SourceItem(Path("landscape.jpg"), 6000, 4000, True)
        self.state.replace_sources([source])
        self.state.set_selected_framing(0.9, 0.25, -0.5)
        plans = []
        self.controller.previewReady.connect(lambda _path, _image, plan, _background: plans.append(plan))
        job = object()
        self.controller._jobs.add(job)
        self.controller._finish_preview(job, source.path, QImage(60, 40, QImage.Format.Format_RGB32), "")
        expected = build_render_plan((6000, 4000), (1080, 1440), 0.9, 0.25, -0.5)
        self.assertEqual(plans, [expected])

    def test_drag_emits_normalized_position_and_zero_for_filled_axis(self) -> None:
        widget = PreviewWidget()
        widget.resize(300, 400)
        plan = build_render_plan((3000, 4000), (1080, 1440), 1.0, 0.0, 0.0)
        widget.set_preview(QPixmap.fromImage(QImage(30, 40, QImage.Format.Format_RGB32)), plan)
        values: list[tuple[float, float]] = []
        widget.framingDragged.connect(lambda x, y: values.append((x, y)))
        widget._drag_start = QPoint(100, 100)
        widget._finish_drag(QPoint(150, 180))
        self.assertEqual(values, [(0.0, 0.0)])

    def test_drag_converts_viewport_displacement_to_free_space_coordinates(self) -> None:
        widget = PreviewWidget()
        widget.resize(540, 720)
        plan = build_render_plan((6000, 4000), (1080, 1440), 1.0, 0.0, 0.0)
        widget.set_preview(QPixmap.fromImage(QImage(60, 40, QImage.Format.Format_RGB32)), plan)
        values: list[tuple[float, float]] = []
        widget.framingDragged.connect(lambda x, y: values.append((x, y)))
        widget._drag_start = QPoint(200, 300)
        widget._finish_drag(QPoint(200, 390))
        self.assertAlmostEqual(values[0][0], 0.0)
        self.assertAlmostEqual(values[0][1], 0.5)

    def test_preview_drag_refreshes_thumbnail_status_to_modified(self) -> None:
        source = SourceItem(Path("master.jpg"), 3000, 4000, True)
        self.state.replace_sources([source])
        self.controller.select(source.path)
        window = MainWindow(controller=self.controller)
        self.addCleanup(window.close)
        self.assertIn("Default", window.thumbnail_view.item(0).text())
        window._preview_dragged(0.25, -0.5)
        self.assertTrue(self.state.is_modified(source.path))
        self.assertIn("Modified", window.thumbnail_view.item(0).text())

    def test_parser_accepts_launcher_arguments(self) -> None:
        args = build_parser().parse_args(["--open", "--source", "masters"])
        self.assertTrue(args.open)
        self.assertEqual(args.source, Path("masters"))

    def test_parser_accepts_handoff_and_output(self) -> None:
        args = build_parser().parse_args(
            ["--open", "--handoff", "select.json", "--output", "framed"]
        )
        self.assertEqual(args.handoff, Path("select.json"))
        self.assertEqual(args.output, Path("framed"))


if __name__ == "__main__":
    unittest.main()
