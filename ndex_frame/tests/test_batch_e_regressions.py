from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageCms
from PySide6.QtWidgets import QApplication

from ndex_frame.core.models import AspectRatio, FramePreset, MetadataPolicy, OutputProfile, OutputSizing
from ndex_frame.imaging.color import prepare_master
from ndex_frame.services.export_job import CancelToken, ExportRequest, plan_export, run_export
from ndex_frame.services.importer import analyze_source
from ndex_frame.services.presets import PresetStore
from ndex_frame.ui.main_window import MainWindow
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState

_CMYK_PROFILE = Path(r"C:\Windows\System32\spool\drivers\color\RSWOP.icm")


def _frame() -> FramePreset:
    return FramePreset("test.frame", "Test", 1, AspectRatio(3, 4), "#FFFFFF", 1.0, 0.0, 0.0)


def _output() -> OutputProfile:
    return OutputProfile(
        "test.output", "Test", 1, OutputSizing("fixed_width", width=30),
        "jpeg", 95, "4:4:4", "sRGB", True, MetadataPolicy(),
    )


class ColorRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        # Windows can still hold the TIFF handle briefly after the image closes.
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    @unittest.skipUnless(_CMYK_PROFILE.exists(), "no CMYK ICC profile available")
    def test_cmyk_image_with_cmyk_profile_converts_without_warning(self) -> None:
        path = self.root / "cmyk.tif"
        Image.new("CMYK", (8, 8), (0, 255, 255, 0)).save(path, icc_profile=_CMYK_PROFILE.read_bytes())
        prepared = prepare_master(path, MetadataPolicy())
        self.addCleanup(prepared.image.close)
        self.assertEqual(prepared.image.mode, "RGB")
        self.assertNotIn("색상 프로필 변환 실패, 기본 변환 사용", prepared.warnings)
        red, green, blue = prepared.image.getpixel((0, 0))
        self.assertGreater(red, green + 60)

    def test_failed_icc_transform_falls_back_with_warning(self) -> None:
        path = self.root / "cmyk.tif"
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        Image.new("CMYK", (8, 8), (0, 0, 0, 0)).save(path, icc_profile=profile)
        error = ImageCms.PyCMSError("cannot build transform")
        with patch("ndex_frame.imaging.color.ImageCms.profileToProfile", side_effect=error):
            prepared = prepare_master(path, MetadataPolicy())
        self.addCleanup(prepared.image.close)
        self.assertEqual(prepared.image.mode, "RGB")
        self.assertIn("색상 프로필 변환 실패, 기본 변환 사용", prepared.warnings)

    def test_16_bit_grayscale_is_scaled_not_clipped(self) -> None:
        path = self.root / "gray16.png"
        Image.new("I;16", (4, 4), 40000).save(path)
        prepared = prepare_master(path, MetadataPolicy())
        self.addCleanup(prepared.image.close)
        red, green, blue = prepared.image.getpixel((0, 0))
        self.assertTrue(154 <= red <= 156, red)
        self.assertEqual((red, green), (green, blue))


class PresetRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for kind in ("frame", "output"):
            (self.root / "presets" / kind).mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _store(self) -> PresetStore:
        return PresetStore(self.root, lambda _s, defaults: dict(defaults), lambda _s, _v: None)

    def _frame_json(self, background: str) -> str:
        return json.dumps({
            "id": "custom.x", "name": "X", "version": 1, "ratio": {"width": 3, "height": 4},
            "background": background, "photo_scale": 1.0, "x": 0.0, "y": 0.0,
        })

    def test_non_utf8_custom_preset_is_reported_not_raised(self) -> None:
        bad = self.root / "presets" / "frame" / "bad.json"
        bad.write_bytes(b"\xff\xfe\x00bad")
        store = self._store()
        self.assertEqual(store.default_frame().id, "builtin.white-3x4")
        self.assertEqual([error.path for error in store.errors], [bad])

    def test_frame_errors_survive_loading_outputs(self) -> None:
        bad = self.root / "presets" / "frame" / "bad.json"
        bad.write_text("{", encoding="utf-8")
        store = self._store()
        store.list_frames()
        store.list_outputs()
        self.assertEqual([error.path for error in store.errors], [bad])
        store.list_frames()
        self.assertEqual(len(store.errors), 1)

    def test_invalid_background_color_is_rejected(self) -> None:
        bad = self.root / "presets" / "frame" / "banana.json"
        bad.write_text(self._frame_json("banana"), encoding="utf-8")
        good = self.root / "presets" / "frame" / "good.json"
        good.write_text(self._frame_json("#abc").replace("custom.x", "custom.good"), encoding="utf-8")
        store = self._store()
        ids = {preset.id: preset for preset in store.list_frames()}
        self.assertNotIn("custom.x", ids)
        self.assertEqual(ids["custom.good"].background, "#AABBCC")
        self.assertEqual([error.path for error in store.errors], [bad])


class ExportContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "input"
        self.output = self.root / "output"
        self.input.mkdir()
        self.output.mkdir()
        self.source = self.input / "a.png"
        Image.new("RGB", (40, 20), (100, 120, 140)).save(self.source)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_result_carries_job_context_from_snapshot(self) -> None:
        snapshot = plan_export(ExportRequest(
            (analyze_source(self.source),), self.output, _frame(), _output(), (), "rename"
        ))
        result = run_export(snapshot, lambda _event: None, CancelToken())
        self.assertEqual(result.output_dir, snapshot.output_dir)
        self.assertEqual(result.source_dir, str(self.input))
        self.assertEqual((result.frame_id, result.output_id), ("test.frame", "test.output"))

    def test_controls_locked_and_export_disabled_while_export_runs(self) -> None:
        state = WorkspaceState(
            [analyze_source(self.source)], working_frame=_frame(), output_profile=_output(),
            output_directory=self.output,
        )
        controller = WorkspaceController(state, settings_writer=lambda _s, _v: None)
        window = MainWindow(controller)
        self.addCleanup(window.close)
        window._sync_controls()
        self.assertTrue(window.export_all_button.isEnabled())
        self.assertTrue(window.open_folder_button.isEnabled())

        controller._export_thread = object()
        try:
            # An import ending mid-export reports "not busy".
            window._busy_changed(False)
            for control in (
                window.export_all_button, window.export_selected_button, window.open_files_button,
                window.open_folder_button, window.output_folder_button, window.frame_preset_combo,
                window.output_profile_combo, window.manage_presets_button, window.save_frame_button,
            ):
                self.assertFalse(control.isEnabled(), control)
            window.set_interactive_dialogs(False)
            window._export_all()  # must not raise inside a slot
            self.assertIn("already running", window.statusBar().currentMessage())
        finally:
            controller._export_thread = None
        window._busy_changed(False)
        self.assertTrue(window.export_all_button.isEnabled())
        self.assertTrue(window.output_folder_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
