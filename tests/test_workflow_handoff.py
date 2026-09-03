"""The four workflow stages, run end to end against one throwaway data root.

PR #9 left four checks to be done by hand: Launcher Continue for all four
apps, Continue falling back to Open Empty when a folder is gone, Image
Manager's Send Picks to Frame, and Frame importing that handoff. This drives
the same code paths without a GUI, so a change to any one stage that breaks
the next one fails here instead of in someone's afternoon.

Only the pixel work is stood in for. Backup scanning and copying, RAW
matching, manifest writing, session merging, and the Launcher's card state
are the real thing.
"""

from __future__ import annotations

import shutil
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from ndex_auto_selector.ndex_auto_selector.services.selector import AutoSelectorService
from ndex_common import session
from ndex_common.manifest import handoff_files, load_manifest
from ndex_common.workflow import (
    record_backup,
    record_export,
    record_extract,
    record_select_handoff,
)
from ndex_launcher.state import gather_workflow_state
from src.backup_executor import execute_backup
from src.scanner import build_scan_items

from tests.test_workflow import patch_roots

SHOT_TIME = datetime(2026, 5, 3, 12, 0, 0)


class _FixedClock:
    """Stands in for EXIF reading: every file was shot at the same moment."""

    def get_capture_datetimes(self, files, logger=None):
        return {path: (SHOT_TIME, "modified_time", False) for path in files}


class HandoffChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

        stack = ExitStack()
        self.addCleanup(stack.close)
        for patcher in patch_roots(self.root):
            stack.enter_context(patcher)

        # A card with one shot per name: the RAW master and its JPG preview.
        self.card = self.root / "card"
        (self.card / "DCIM").mkdir(parents=True)
        for number in ("0001", "0002", "0003"):
            (self.card / "DCIM" / f"IMG_{number}.CR3").write_text(f"raw-{number}", encoding="utf-8")
            (self.card / "DCIM" / f"IMG_{number}.JPG").write_bytes(f"jpg-{number}".encode())
        self.library = self.root / "library"

    def steps(self) -> dict[str, object]:
        return {step.key: step for step in gather_workflow_state()}

    # --- the four stages ------------------------------------------------

    def backup(self) -> Path:
        """Stage 1: NDEX One copies the card into the date-based library."""
        files = sorted((self.card / "DCIM").iterdir())
        items, _counts = build_scan_items(files, self.library, _FixedClock())
        result = execute_backup(items, duplicate_policy="rename", verify_mode="sha256")
        self.assertEqual(result.errors, 0)
        manifest_path = record_backup(self.card, self.library, result)
        assert manifest_path is not None
        return manifest_path

    def backed_up(self, file_type: str) -> Path:
        return self.library / "2026" / "05" / "0503" / file_type

    def picked_jpgs(self) -> list[Path]:
        """The two JPGs the photographer keeps out of the three shot."""
        return sorted(self.backed_up("jpg").glob("IMG_000[12].JPG"))

    def send_picks(self, picks: list[Path]) -> Path:
        """Stage 2: Image Manager hands the picked JPGs to Frame."""
        manifest_path = record_select_handoff(self.backed_up("jpg"), picks)
        assert manifest_path is not None
        return manifest_path

    def copy_to_selected(self, picks: list[Path]) -> Path:
        selected = self.root / "selected"
        selected.mkdir(exist_ok=True)
        for pick in picks:
            (selected / pick.name).write_bytes(pick.read_bytes())
        return selected

    def extract(self, picks: list[Path]) -> Path:
        """Stage 3: Auto Selector pulls the RAW masters for those picks."""
        selected = self.copy_to_selected(picks)
        work = self.root / "work"

        service = AutoSelectorService()
        summary = service.analyze(self.backed_up("cr3"), selected)
        result = service.copy_matches(summary.matches, work, "rename")
        self.assertEqual(result.copied, len(picks))
        manifest_path = record_extract(selected, self.backed_up("cr3"), work, result, recursive=True)
        assert manifest_path is not None
        return manifest_path

    def export(self, handoff: Path) -> tuple[Path, list[Path]]:
        """Stage 4: Frame imports the handoff and exports what it read."""
        payload = load_manifest(handoff)
        assert payload is not None
        imported = handoff_files(payload)

        output = self.root / "instagram"
        output.mkdir(exist_ok=True)
        items = []
        for source in imported:
            destination = output / f"{source.stem}.jpg"
            destination.write_bytes(b"framed")
            items.append(
                SimpleNamespace(source=source, destination=destination, state="exported", message="")
            )
        result = SimpleNamespace(exported=len(items), skipped=0, failed=0, cancelled=False, items=items)
        manifest_path = record_export(
            self.backed_up("jpg"), output, result, frame_preset="square", output_profile="jpeg"
        )
        assert manifest_path is not None
        return manifest_path, imported

    # --- tests ----------------------------------------------------------

    def test_four_stages_leave_the_launcher_able_to_continue_each_one(self) -> None:
        self.backup()
        picks = self.picked_jpgs()
        self.assertEqual(len(picks), 2)
        handoff = self.send_picks(picks)
        self.extract(picks)
        _export_manifest, imported = self.export(handoff)

        # Frame imported exactly the picks, not the whole backed-up folder.
        self.assertEqual([path.name for path in imported], [pick.name for pick in picks])

        steps = self.steps()

        self.assertEqual(
            steps["ndex_one"].launch_args,
            ["--open", "--source", str(self.card), "--destination", str(self.library)],
        )
        self.assertEqual(
            steps["image_manager"].launch_args,
            ["--open", "--source", str(self.backed_up("jpg"))],
        )
        self.assertEqual(
            steps["auto_selector"].launch_args,
            [
                "--open",
                "--selected-jpg",
                str(self.root / "selected"),
                "--raw-source",
                str(self.backed_up("cr3")),
                "--work-folder",
                str(self.root / "work"),
            ],
        )
        # Frame continues from the handoff, not from a folder, and still
        # reopens the folder it exported into last time.
        self.assertEqual(
            steps["frame"].launch_args,
            ["--open", "--handoff", str(handoff), "--output", str(self.root / "instagram")],
        )

        # Every card reports its own last job, not another app's.
        self.assertTrue(steps["ndex_one"].result_text.startswith("Backup - "))
        self.assertTrue(steps["image_manager"].result_text.startswith("Send to Frame - "))
        self.assertTrue(steps["auto_selector"].result_text.startswith("Extract - "))
        self.assertTrue(steps["frame"].result_text.startswith("Export - "))
        self.assertIn("2 exported", steps["frame"].result_text)

    def test_each_stage_records_the_folders_the_next_stage_needs(self) -> None:
        backup_manifest = self.backup()
        picks = self.picked_jpgs()
        handoff = self.send_picks(picks)
        extract_manifest = self.extract(picks)
        export_manifest, _imported = self.export(handoff)

        folders = {
            path: (load_manifest(path) or {}).get("folders", {})
            for path in (backup_manifest, handoff, extract_manifest, export_manifest)
        }
        self.assertEqual(folders[backup_manifest]["destination"], str(self.library))
        self.assertEqual(folders[handoff]["source"], str(self.backed_up("jpg")))
        # The RAW folder is what a retry of the extract has to search again.
        self.assertEqual(folders[extract_manifest]["raw_source"], str(self.backed_up("cr3")))
        self.assertEqual(folders[export_manifest]["output"], str(self.root / "instagram"))

    def test_continue_falls_back_to_open_empty_when_the_folder_is_gone(self) -> None:
        self.backup()
        self.assertNotEqual(self.steps()["ndex_one"].launch_args, ["--open"])

        shutil.rmtree(self.card)

        step = self.steps()["ndex_one"]
        # The library is still there, so Continue drops only the missing half.
        self.assertEqual(step.launch_args, ["--open", "--destination", str(self.library)])
        self.assertEqual(step.status_text, f"Last: {self.library}")

        shutil.rmtree(self.library)
        step = self.steps()["ndex_one"]
        self.assertEqual(step.launch_args, ["--open"])
        self.assertEqual(step.status_text, f"Last folder missing: {self.library}")

    def test_frame_stops_offering_a_handoff_whose_files_are_gone(self) -> None:
        self.backup()
        picks = self.picked_jpgs()
        handoff = self.send_picks(picks)
        self.assertIn("--handoff", self.steps()["frame"].launch_args)

        for pick in picks:
            pick.unlink()

        step = self.steps()["frame"]
        self.assertFalse(step.handoff_ready)
        # The manifest is still on disk; it is the files it lists that are not.
        self.assertTrue(handoff.is_file())
        # Continue offers the folder the picks came from instead of a list
        # Frame would open empty.
        self.assertEqual(step.launch_args, ["--open", "--source", str(self.backed_up("jpg"))])

        shutil.rmtree(self.backed_up("jpg"))
        self.assertEqual(self.steps()["frame"].launch_args, ["--open"])

    def test_extract_reports_a_pick_whose_raw_master_was_never_backed_up(self) -> None:
        self.backup()
        picks = self.picked_jpgs()
        (self.backed_up("cr3") / "IMG_0002.CR3").unlink()

        self.send_picks(picks)
        selected = self.copy_to_selected(picks)
        work = self.root / "work"

        service = AutoSelectorService()
        summary = service.analyze(self.backed_up("cr3"), selected)
        result = service.copy_matches(summary.matches, work, "rename")
        manifest_path = record_extract(selected, self.backed_up("cr3"), work, result, recursive=True)
        assert manifest_path is not None

        payload = load_manifest(manifest_path) or {}
        missing = [item for item in payload["items"] if item["status"] == "missing"]
        self.assertEqual([Path(item["path"]).name for item in missing], ["IMG_0002.JPG"])
        self.assertIn("1 missing", self.steps()["auto_selector"].result_text)


if __name__ == "__main__":
    unittest.main()
