from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ndex_common import manifest, session
from ndex_common.workflow import (
    record_backup,
    record_export,
    record_extract,
    record_select_handoff,
    trim_items,
)


def patch_roots(root: Path):
    """Point settings, sessions, and manifests at a throwaway folder."""
    settings_file = root / "config" / "settings.json"
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    return (
        patch("ndex_common.session.data_dir", return_value=root),
        patch("ndex_common.manifest.data_dir", return_value=root),
        patch("ndex_common.settings.data_dir", return_value=root),
        patch("ndex_common.settings.settings_path", return_value=settings_file),
        patch("ndex_common.settings._config_dir", return_value=settings_file.parent),
    )


class WorkflowRecordTests(unittest.TestCase):
    def _patch_roots(self, root: Path):
        return patch_roots(root)

    def test_select_handoff_writes_sidecar_and_frame_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root / "photos"
            photos.mkdir()
            pick = photos / "pick.jpg"
            pick.write_bytes(b"jpg")
            patches = self._patch_roots(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                path = record_select_handoff(photos, [pick])
                loaded = manifest.load_manifest(path)
                frame = session.load_session("frame", root=root)
                stored = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))

            self.assertIsNotNone(path)
            assert path is not None
            self.assertTrue(path.is_file())
            self.assertEqual(path.parent.resolve(), (root / "manifests").resolve())
            self.assertEqual(loaded["type"], "select_handoff")
            self.assertEqual(loaded["items"][0]["path"], str(pick))
            self.assertFalse(any(photos.glob("*.json")))
            self.assertEqual(frame["context"]["handoff"], str(path))
            self.assertNotIn("files", stored["shared"]["sessions"]["image_manager"]["context"])
            self.assertEqual(stored["schema_version"], 1)

    def test_backup_and_export_count_copied_skipped_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self._patch_roots(root)
            backup_result = SimpleNamespace(
                copied=2,
                skipped=1,
                errors=0,
                overwritten=0,
                cancelled=False,
                messages=["copied a"],
                items=[{"path": "a.CR3", "status": "copied"}],
            )
            export_result = SimpleNamespace(
                exported=1,
                skipped=0,
                failed=1,
                cancelled=False,
                items=[
                    SimpleNamespace(source="in.jpg", destination="out.jpg", state="exported", message=""),
                    SimpleNamespace(source="bad.jpg", destination="", state="failed", message="boom"),
                ],
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                backup = record_backup("E:/DCIM", "D:/Lib", backup_result)
                export = record_export("D:/Masters", "D:/Framed", export_result, frame_preset="builtin.white-3x4")
                backup_doc = manifest.load_manifest(backup)
                export_doc = manifest.load_manifest(export)

            self.assertEqual(backup_doc["counts"]["copied"], 2)
            self.assertEqual(backup_doc["counts"]["skipped"], 1)
            self.assertEqual(export_doc["counts"]["failed"], 1)
            self.assertEqual(export_doc["context"]["frame_preset"], "builtin.white-3x4")
    def test_manifest_survives_a_failed_session_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root / "photos"
            photos.mkdir()
            pick = photos / "pick.jpg"
            pick.write_bytes(b"jpg")
            patches = self._patch_roots(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                with patch("ndex_common.session.remember", side_effect=OSError("locked")):
                    path = record_select_handoff(photos, [pick])

            self.assertIsNotNone(path)
            assert path is not None
            self.assertTrue(path.is_file())
            self.assertEqual(manifest.load_manifest(path)["items"][0]["path"], str(pick))

class RetryRecordTests(unittest.TestCase):
    """What a retry needs the manifest to carry."""

    def _patch_roots(self, root: Path):
        return patch_roots(root)

    def test_backup_items_reach_the_manifest(self) -> None:
        result = SimpleNamespace(
            copied=1,
            skipped=0,
            errors=1,
            overwritten=0,
            cancelled=False,
            messages=[],
            items=[
                {"path": "E:/DCIM/a.CR3", "status": "copied", "destination": "D:/Lib/a.CR3"},
                {"path": "E:/DCIM/b.CR3", "status": "failed", "detail": "disk full"},
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self._patch_roots(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                path = record_backup("E:/DCIM", "D:/Lib", result)
                loaded = manifest.load_manifest(path)

        self.assertEqual([item["path"] for item in loaded["items"]], ["E:/DCIM/a.CR3", "E:/DCIM/b.CR3"])
        self.assertEqual(loaded["items"][1]["status"], "failed")

    def test_extract_manifest_keeps_the_raw_folder_a_retry_needs(self) -> None:
        result = SimpleNamespace(
            copied=1, skipped=0, ambiguous=0, missing=1, errors=0, items=[]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self._patch_roots(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                path = record_extract("D:/Selected", "E:/RAW", "D:/Work", result, recursive=False)
                loaded = manifest.load_manifest(path)

        self.assertEqual(loaded["folders"]["raw_source"], "E:/RAW")
        self.assertEqual(loaded["folders"]["work"], "D:/Work")
        self.assertIs(loaded["context"]["recursive"], False)

    def test_a_retry_marks_which_job_it_came_from(self) -> None:
        result = SimpleNamespace(
            copied=1, skipped=0, errors=0, overwritten=0, cancelled=False, messages=[], items=[]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self._patch_roots(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                path = record_backup(
                    "E:/DCIM",
                    "D:/Lib",
                    result,
                    context={"retry_of": "backup-20260902T101500Z.json", "retried": 3},
                )
                loaded = manifest.load_manifest(path)

        self.assertEqual(loaded["context"]["retry_of"], "backup-20260902T101500Z.json")
        self.assertEqual(loaded["context"]["retried"], 3)
        self.assertFalse(loaded["context"]["cancelled"])

    def test_export_keeps_its_own_context_alongside_the_retry_marker(self) -> None:
        result = SimpleNamespace(exported=1, skipped=0, failed=0, cancelled=False, items=[])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self._patch_roots(root)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                path = record_export(
                    "D:/Picks",
                    "D:/Out",
                    result,
                    frame_preset="white-3-4",
                    output_profile="ig-feed",
                    context={"retry_of": "export-1.json"},
                )
                loaded = manifest.load_manifest(path)

        self.assertEqual(loaded["context"]["frame_preset"], "white-3-4")
        self.assertEqual(loaded["context"]["retry_of"], "export-1.json")


class TrimItemsTests(unittest.TestCase):
    def test_problems_are_always_kept_and_successes_are_capped(self) -> None:
        items = [{"path": f"a{index}.CR3", "status": "copied"} for index in range(5)]
        items.append({"path": "bad.CR3", "status": "failed", "detail": "disk full"})
        items.append({"path": "b.CR3", "status": "skipped"})

        kept = trim_items(items, keep=2)

        statuses = [item["status"] for item in kept]
        self.assertEqual(statuses.count("copied"), 3)  # 2 kept + the closing record
        self.assertIn({"path": "bad.CR3", "status": "failed", "detail": "disk full"}, kept)
        self.assertEqual(kept[-1], {"path": "", "status": "copied", "detail": "+3 more not listed"})
        self.assertEqual(statuses.count("skipped"), 1)

    def test_nothing_is_added_when_under_the_cap(self) -> None:
        items = [{"path": "a.CR3", "status": "copied"}]
        self.assertEqual(trim_items(items, keep=2), items)



if __name__ == "__main__":
    unittest.main()
