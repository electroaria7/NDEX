from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QImage

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


class _QueuedPool:
    def __init__(self) -> None:
        self.jobs = []

    def start(self, job) -> None:
        self.jobs.append(job)


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
                SourceItem(self.second_path, 6000, 4000, False, ("No colour profile — treated as sRGB",)),
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

    def test_late_import_cannot_replace_the_newest_request(self) -> None:
        pool = _QueuedPool()
        controller = WorkspaceController(self.workspace, thread_pool=pool, settings_writer=lambda *_: None)
        busy = []
        controller.busyChanged.connect(busy.append)
        controller.import_paths([Path("old")])
        first = pool.jobs[-1]
        controller.import_paths([Path("new")])
        second = pool.jobs[-1]
        controller._finish_import(first, [self.workspace.sources[0]])
        self.assertTrue(busy[-1])
        newest = self.workspace.sources[1]
        controller._finish_import(second, [newest])
        self.assertEqual(controller.state.sources, [newest])
        self.assertFalse(busy[-1])

    def test_preview_failure_does_not_finish_an_import(self) -> None:
        pool = _QueuedPool()
        controller = WorkspaceController(self.workspace, thread_pool=pool, settings_writer=lambda *_: None)
        busy = []
        controller.busyChanged.connect(busy.append)
        controller.request_preview(self.first_path)
        preview = pool.jobs[-1]
        controller.import_paths([Path("next")])
        controller._fail_job(preview, "Unreadable preview")
        self.assertTrue(busy[-1])

    def test_old_import_finishing_last_cannot_overwrite_new_sources(self) -> None:
        pool = _QueuedPool()
        controller = WorkspaceController(self.workspace, thread_pool=pool, settings_writer=lambda *_: None)
        original, newest = self.workspace.sources
        controller.import_paths([Path("old")])
        first = pool.jobs[-1]
        controller.import_paths([Path("new")])
        second = pool.jobs[-1]
        controller._finish_import(second, [newest])
        controller._finish_import(first, [original])
        self.assertEqual(controller.state.sources, [newest])

    def test_source_change_during_preview_decode_drops_the_old_image(self) -> None:
        pool = _QueuedPool()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "photo.jpg"
            path.write_bytes(b"first")
            self.workspace.replace_sources([SourceItem(path, 3000, 4000, True)])
            controller = WorkspaceController(self.workspace, thread_pool=pool, settings_writer=lambda *_: None)
            previews = []
            controller.previewReady.connect(lambda *_: previews.append(True))
            controller.request_preview(path)
            path.write_bytes(b"changed photo")
            controller._finish_preview(pool.jobs[0], path, QImage(30, 40, QImage.Format.Format_RGB32), "")
            self.assertEqual(previews, [])
            controller.request_preview(path)
            self.assertEqual(len(pool.jobs), 2)

    def test_framing_changes_reuse_decoded_preview_and_invalidate_on_file_change(self) -> None:
        pool = _QueuedPool()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "photo.jpg"
            source.write_bytes(b"first version")
            self.workspace.replace_sources([SourceItem(source, 3000, 4000, True)])
            controller = WorkspaceController(self.workspace, thread_pool=pool, settings_writer=lambda *_: None)
            previews = []
            controller.previewReady.connect(lambda *_: previews.append(True))
            for step in range(20):
                controller.set_selected_framing(.8, step / 20, 0)
            self.assertEqual(len(pool.jobs), 1)
            controller._finish_preview(pool.jobs[0], source, QImage(30, 40, QImage.Format.Format_RGB32), "")
            controller.set_selected_framing(.9, 0, 0)
            self.assertEqual(len(pool.jobs), 1)
            self.assertEqual(len(previews), 2)
            source.write_bytes(b"changed version with new size")
            controller.request_preview(source)
            self.assertEqual(len(pool.jobs), 2)


if __name__ == "__main__":
    unittest.main()
