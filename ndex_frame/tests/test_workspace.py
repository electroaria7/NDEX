from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_frame.core.models import (
    AspectRatio,
    FramePreset,
    MetadataPolicy,
    OutputProfile,
    OutputSizing,
    SourceItem,
)
from ndex_frame.services.export_job import CancelToken, ExportResult
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState


class WorkspaceStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first_path = Path("first.jpg")
        self.second_path = Path("second.jpg")
        self.frame = FramePreset(
            "frame", "Frame", 1, AspectRatio(3, 4), "#FFFFFF", 1.0, 0.0, 0.0
        )
        self.output = OutputProfile(
            "output",
            "Output",
            1,
            OutputSizing("fixed_width", width=1080),
            "jpeg",
            95,
            "4:4:4",
            "sRGB",
            True,
            MetadataPolicy(),
        )
        self.workspace = WorkspaceState(
            sources=[
                SourceItem(self.first_path, 3000, 4000, True),
                SourceItem(self.second_path, 6000, 4000, False, ("색상 프로필 없음",)),
            ],
            working_frame=self.frame,
            output_profile=self.output,
        )

    def test_selected_image_inherits_frame_until_modified(self) -> None:
        self.assertEqual(self.workspace.selected_path, self.first_path)
        self.assertFalse(self.workspace.is_modified(self.first_path))
        self.workspace.set_selected_framing(photo_scale=0.9, x=0.0, y=0.2)
        self.assertTrue(self.workspace.is_modified(self.first_path))
        self.assertFalse(self.workspace.is_modified(self.second_path))
        self.assertEqual(self.workspace.effective_framing(self.first_path), (0.9, 0.0, 0.2))
        self.assertEqual(self.workspace.effective_framing(self.second_path), (1.0, 0.0, 0.0))

    def test_apply_to_all_changes_base_and_clears_overrides(self) -> None:
        self.workspace.set_selected_framing(0.9, 0.0, 0.2)
        self.workspace.apply_current_framing_to_all()
        self.assertEqual(self.workspace.working_frame.photo_scale, 0.9)
        self.assertEqual(self.workspace.working_frame.y, 0.2)
        self.assertEqual(self.workspace.overrides, {})

    def test_reset_override_removes_only_selected_override(self) -> None:
        self.workspace.set_selected_framing(0.9, 0.1, 0.2)
        self.workspace.select(self.second_path)
        self.workspace.set_selected_framing(0.8, -0.1, -0.2)
        self.workspace.reset_override(self.second_path)
        self.assertTrue(self.workspace.is_modified(self.first_path))
        self.assertFalse(self.workspace.is_modified(self.second_path))

    def test_replacing_sources_preserves_order_and_selects_first(self) -> None:
        self.workspace.replace_sources(list(reversed(self.workspace.sources)))
        self.assertEqual([item.path for item in self.workspace.sources], [self.second_path, self.first_path])
        self.assertEqual(self.workspace.selected_path, self.second_path)
        self.assertEqual(self.workspace.overrides, {})

    def test_export_cleanup_waits_for_thread_finished_and_next_job_can_start(self) -> None:
        controller = WorkspaceController(
            self.workspace, settings_writer=lambda _section, _values: None
        )
        token = CancelToken()
        pending = ExportResult(0, 0, 0, False, ())
        thread_marker = object()
        worker_marker = object()
        controller._export_thread = thread_marker
        controller._export_worker = worker_marker
        controller._cancel_token = token
        busy: list[bool] = []
        finished: list[ExportResult] = []
        controller.busyChanged.connect(busy.append)
        controller.exportFinished.connect(finished.append)

        controller._record_export_result(pending)
        self.assertIs(controller._export_thread, thread_marker)
        self.assertIs(controller._export_worker, worker_marker)
        self.assertIs(controller._cancel_token, token)
        self.assertEqual(busy, [])
        self.assertEqual(finished, [])
        with self.assertRaisesRegex(RuntimeError, "already running"):
            controller.start_export()

        controller._export_thread_finished()
        self.assertIsNone(controller._export_thread)
        self.assertIsNone(controller._export_worker)
        self.assertIsNone(controller._cancel_token)
        self.assertEqual(busy, [False])
        self.assertEqual(finished, [pending])

        class PlannedAgain(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            self.workspace.output_directory = Path(directory)
            with patch("ndex_frame.ui.workspace.plan_export", side_effect=PlannedAgain):
                with self.assertRaises(PlannedAgain):
                    controller.start_export()


if __name__ == "__main__":
    unittest.main()
