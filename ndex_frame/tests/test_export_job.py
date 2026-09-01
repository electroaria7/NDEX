from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ndex_frame.core.models import (
    AspectRatio,
    FramePreset,
    ImageOverride,
    MetadataPolicy,
    OutputProfile,
    OutputSizing,
    SourceItem,
)
from ndex_frame.services.export_job import CancelToken, ExportRequest, plan_export, run_export


class ExportJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.input = self.root / "input"
        self.output = self.root / "output"
        self.input.mkdir()
        self.output.mkdir()
        self.source_path = self.input / "IMG_001.png"
        Image.new("RGB", (40, 20), (100, 120, 140)).save(self.source_path)
        self.frame = FramePreset(
            "test.frame", "Test Frame", 1, AspectRatio(3, 4), "#ffffff", 1.0, 0.0, 0.0
        )
        self.profile = OutputProfile(
            "test.output",
            "Test Output",
            1,
            OutputSizing("fixed_width", width=30),
            "jpeg",
            95,
            "4:4:4",
            "sRGB",
            True,
            MetadataPolicy(),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def source(self, path: Path | None = None) -> SourceItem:
        return SourceItem(path or self.source_path, 40, 20, False, ("색상 프로필 없음",))

    def request(
        self,
        *,
        sources: tuple[SourceItem, ...] | None = None,
        collision_policy: str = "skip",
        overrides: tuple[ImageOverride, ...] = (),
    ) -> ExportRequest:
        return ExportRequest(
            sources=sources or (self.source(),),
            output_dir=self.output,
            frame=self.frame,
            output=self.profile,
            overrides=overrides,
            collision_policy=collision_policy,  # type: ignore[arg-type]
        )

    def test_existing_file_is_skipped_without_overwrite(self) -> None:
        existing = self.output / "IMG_001.jpg"
        existing.write_bytes(b"keep")

        snapshot = plan_export(self.request(collision_policy="skip"))

        self.assertEqual(snapshot.items[0].action, "skip")
        self.assertEqual(existing.read_bytes(), b"keep")

    def test_rename_policy_uses_incrementing_suffix(self) -> None:
        (self.output / "IMG_001.jpg").write_bytes(b"one")
        (self.output / "IMG_001_01.jpg").write_bytes(b"two")

        snapshot = plan_export(self.request(collision_policy="rename"))

        self.assertEqual(snapshot.items[0].destination.name, "IMG_001_02.jpg")

    def test_rename_reserves_names_across_the_batch_without_creating_outputs(self) -> None:
        second_dir = self.root / "second"
        second_dir.mkdir()
        second = second_dir / "IMG_001.png"
        Image.new("RGB", (40, 20), "navy").save(second)

        snapshot = plan_export(
            self.request(sources=(self.source(), self.source(second)), collision_policy="rename")
        )

        self.assertEqual([item.destination.name for item in snapshot.items], ["IMG_001.jpg", "IMG_001_01.jpg"])
        self.assertEqual(list(self.output.glob("*.jpg")), [])
        self.assertEqual(list(self.output.glob("*.ndex_probe")), [])

    def test_override_is_snapshotted_into_render_plan(self) -> None:
        override = ImageOverride(self.source_path, 0.5, 1.0, -1.0)

        snapshot = plan_export(self.request(overrides=(override,)))

        plan = snapshot.items[0].render_plan
        self.assertEqual((plan.canvas_width, plan.canvas_height), (30, 40))
        self.assertEqual((plan.photo_width, plan.photo_height), (15, 8))
        self.assertEqual((plan.left, plan.top), (15, 0))

    def test_invalid_collision_policy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan_export(self.request(collision_policy="replace"))

    def test_one_failed_source_does_not_stop_remaining_items(self) -> None:
        good_two = self.input / "IMG_003.png"
        Image.new("RGB", (20, 40), "green").save(good_two)
        bad = self.input / "IMG_002.png"
        bad.write_bytes(b"not an image")
        snapshot = plan_export(
            self.request(
                sources=(self.source(), self.source(bad), self.source(good_two)),
                collision_policy="rename",
            )
        )

        events = []
        result = run_export(snapshot, progress=events.append, cancel=CancelToken())

        self.assertEqual((result.exported, result.failed, result.skipped), (2, 1, 0))
        self.assertFalse(result.cancelled)
        self.assertEqual([item.state for item in result.items], ["exported", "failed", "exported"])
        self.assertTrue((self.output / "IMG_001.jpg").is_file())
        self.assertTrue((self.output / "IMG_003.jpg").is_file())
        self.assertEqual(events[-1].state, "exported")

    def test_cancel_keeps_completed_outputs_and_removes_temp_files(self) -> None:
        paths = []
        for number in range(1, 4):
            path = self.input / f"photo_{number}.png"
            Image.new("RGB", (40, 20), (number * 20, 30, 40)).save(path)
            paths.append(path)
        token = CancelToken()

        def progress(event: object) -> None:
            if getattr(event, "state") == "exported":
                token.cancel()

        snapshot = plan_export(
            self.request(sources=tuple(self.source(path) for path in paths), collision_policy="rename")
        )
        result = run_export(snapshot, progress, token)

        self.assertEqual(result.exported, 1)
        self.assertTrue(result.cancelled)
        self.assertEqual(len(list(self.output.glob("*.jpg"))), 1)
        self.assertEqual(list(self.output.glob("*.ndex_tmp")), [])

    def test_skip_items_are_counted_without_decoding_sources(self) -> None:
        (self.output / "IMG_001.jpg").write_bytes(b"existing")
        self.source_path.write_bytes(b"now corrupt")

        result = run_export(plan_export(self.request()), lambda event: None, CancelToken())

        self.assertEqual((result.exported, result.skipped, result.failed), (0, 1, 0))
        self.assertEqual((self.output / "IMG_001.jpg").read_bytes(), b"existing")

    def test_exported_progress_error_does_not_double_count_or_stop_batch(self) -> None:
        second = self.input / "IMG_002.png"
        Image.new("RGB", (40, 20), "green").save(second)
        snapshot = plan_export(
            self.request(sources=(self.source(), self.source(second)), collision_policy="rename")
        )

        def broken_after_export(event: object) -> None:
            if getattr(event, "state") == "exported":
                raise RuntimeError("observer failed")

        result = run_export(snapshot, broken_after_export, CancelToken())

        self.assertEqual((result.exported, result.failed, result.skipped), (2, 0, 0))
        self.assertEqual([item.state for item in result.items], ["exported", "exported"])
        self.assertTrue((self.output / "IMG_001.jpg").is_file())
        self.assertTrue((self.output / "IMG_002.jpg").is_file())

    def test_progress_observer_errors_are_ignored_for_every_state(self) -> None:
        existing = self.output / "IMG_001.jpg"
        existing.write_bytes(b"keep")

        def always_broken(event: object) -> None:
            raise RuntimeError("observer failed")

        result = run_export(plan_export(self.request()), always_broken, CancelToken())

        self.assertEqual((result.exported, result.failed, result.skipped), (0, 0, 1))
        self.assertEqual(existing.read_bytes(), b"keep")

    def test_progress_keyboard_interrupt_propagates(self) -> None:
        def interrupted(event: object) -> None:
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_export(plan_export(self.request()), interrupted, CancelToken())

    def test_progress_system_exit_propagates(self) -> None:
        def exiting(event: object) -> None:
            raise SystemExit(7)

        with self.assertRaises(SystemExit) as raised:
            run_export(plan_export(self.request()), exiting, CancelToken())

        self.assertEqual(raised.exception.code, 7)


if __name__ == "__main__":
    unittest.main()
