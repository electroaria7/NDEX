from __future__ import annotations

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog

from ndex_frame.core.geometry import build_render_plan, project_render_plan
from ndex_frame.core.models import AspectRatio, FramePreset, MetadataPolicy, OutputProfile, OutputSizing, SourceItem
from ndex_frame.main import build_parser
from ndex_frame.ui.main_window import MainWindow
from ndex_frame.ui.preview_widget import PreviewWidget
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState


class MainWindowTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
