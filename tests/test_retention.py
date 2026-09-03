from __future__ import annotations

import unittest
import unittest.mock
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from ndex_common import session
from ndex_common.jsonio import write_json_atomic
from ndex_common.manifest import manifests_dir
from ndex_common.report import path_key, recent_reports
from ndex_common.retention import pinned_paths, prune_manifests
from ndex_common.workflow import record_backup, record_select_handoff

from tests.test_workflow import patch_roots


class RetentionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        stack = ExitStack()
        self.addCleanup(stack.close)
        for patcher in patch_roots(self.root):
            stack.enter_context(patcher)

    def write(self, name: str, *, app: str = "ndex_one", type: str = "backup") -> Path:
        """Put a manifest in the folder under an exact name."""
        path = manifests_dir() / name
        write_json_atomic(
            path,
            {
                "kind": "ndex.manifest",
                "schema_version": 1,
                "type": type,
                "app": app,
                "created_at": "2026-05-03T12:00:00Z",
                "counts": {"copied": 1},
                "items": [],
            },
        )
        return path

    def stamps(self, count: int, *, type: str = "backup", app: str = "ndex_one") -> list[Path]:
        return [
            self.write(f"{type}-202605{day:02d}T120000Z.json", app=app, type=type)
            for day in range(1, count + 1)
        ]

    def names(self) -> set[str]:
        return {path.name for path in manifests_dir().glob("*.json")}


class PruneTests(RetentionTestCase):
    def test_keeps_the_newest_and_deletes_the_rest_of_that_type(self) -> None:
        self.stamps(5)

        deleted = prune_manifests(keep=2)

        self.assertEqual(
            [path.name for path in deleted],
            ["backup-20260503T120000Z.json", "backup-20260502T120000Z.json", "backup-20260501T120000Z.json"],
        )
        self.assertEqual(
            self.names(),
            {"backup-20260505T120000Z.json", "backup-20260504T120000Z.json"},
        )

    def test_counts_each_type_on_its_own(self) -> None:
        self.stamps(3, type="backup", app="ndex_one")
        self.stamps(3, type="export", app="frame")
        self.stamps(3, type="select_handoff", app="image_manager")

        prune_manifests(keep=2)

        remaining = self.names()
        self.assertEqual(len(remaining), 6)
        for type_name in ("backup", "export", "select_handoff"):
            kept = {name for name in remaining if name.startswith(type_name)}
            self.assertEqual(len(kept), 2, type_name)

    def test_same_second_manifests_order_by_their_suffix(self) -> None:
        first = self.write("backup-20260503T120000Z.json")
        second = self.write("backup-20260503T120000Z-2.json")
        third = self.write("backup-20260503T120000Z-3.json")

        prune_manifests(keep=2)

        self.assertFalse(first.is_file())
        self.assertTrue(second.is_file())
        self.assertTrue(third.is_file())

    def test_never_deletes_the_latest_pointer_or_a_stranger(self) -> None:
        self.stamps(3)
        pointer = self.write("latest-ndex_one-backup.json")
        stranger = manifests_dir() / "notes.json"
        stranger.write_text("{}", encoding="utf-8")

        prune_manifests(keep=1)

        self.assertTrue(pointer.is_file())
        self.assertTrue(stranger.is_file())

    def test_the_default_reads_the_constant_at_call_time(self) -> None:
        self.stamps(4)

        with unittest.mock.patch("ndex_common.retention.KEEP_PER_TYPE", 1):
            prune_manifests()

        self.assertEqual(self.names(), {"backup-20260504T120000Z.json"})

    def test_keeps_one_even_when_asked_for_none(self) -> None:
        self.stamps(3)

        prune_manifests(keep=0)

        self.assertEqual(self.names(), {"backup-20260503T120000Z.json"})

    def test_leaves_a_manifest_a_session_still_opens_on(self) -> None:
        paths = self.stamps(5)
        oldest = paths[0]
        session.remember("ndex_one", last_manifest=str(oldest))

        prune_manifests(keep=2)

        self.assertTrue(oldest.is_file())
        # Two kept by the cap, plus the pinned one the cap would have dropped.
        self.assertEqual(len(self.names()), 3)

    def test_leaves_the_handoff_frame_would_import(self) -> None:
        paths = self.stamps(5, type="select_handoff", app="image_manager")
        oldest = paths[0]
        session.remember("frame", context={"handoff": str(oldest)})

        prune_manifests(keep=2)

        self.assertTrue(oldest.is_file())

    def test_a_pin_survives_a_wiped_sessions_folder(self) -> None:
        paths = self.stamps(5)
        oldest = paths[0]
        session.remember("ndex_one", last_manifest=str(oldest))
        for stale in (self.root / "sessions").glob("*.json"):
            stale.unlink()

        # Only the shared.sessions snapshot in settings.json is left.
        self.assertEqual(pinned_paths(), {path_key(oldest)})
        prune_manifests(keep=2)

        self.assertTrue(oldest.is_file())

    def test_survives_a_manifests_folder_it_cannot_read(self) -> None:
        self.stamps(3)
        with unittest.mock.patch.object(Path, "glob", side_effect=OSError("busy")):
            self.assertEqual(prune_manifests(keep=1), [])
        self.assertEqual(len(self.names()), 3)

    def test_a_file_that_will_not_delete_does_not_stop_the_others(self) -> None:
        paths = self.stamps(4)
        real_unlink = Path.unlink

        def refuse(self_path, *args, **kwargs):
            if self_path.name == paths[1].name:
                raise PermissionError("open elsewhere")
            return real_unlink(self_path, *args, **kwargs)

        with unittest.mock.patch.object(Path, "unlink", refuse):
            deleted = prune_manifests(keep=2)

        self.assertEqual([path.name for path in deleted], [paths[0].name])
        self.assertTrue(paths[1].is_file())


class RecordingPrunesTests(RetentionTestCase):
    def test_recording_a_job_trims_the_folder_behind_it(self) -> None:
        self.stamps(4)
        result = SimpleNamespace(copied=1, skipped=0, errors=0, overwritten=0, items=[], messages=[])

        with unittest.mock.patch("ndex_common.retention.KEEP_PER_TYPE", 2):
            written = record_backup(self.root / "card", self.root / "library", result)

        assert written is not None
        self.assertTrue(written.is_file())
        # The new one, plus the newest of the four that were already there.
        kept = sorted(name for name in self.names() if not name.startswith("latest-"))
        self.assertEqual(kept, ["backup-20260504T120000Z.json", written.name])

    def test_a_fresh_handoff_is_never_pruned_out_from_under_frame(self) -> None:
        photos = self.root / "photos"
        photos.mkdir()
        pick = photos / "pick.jpg"
        pick.write_bytes(b"jpg")
        self.stamps(4, type="select_handoff", app="image_manager")

        with unittest.mock.patch("ndex_common.retention.KEEP_PER_TYPE", 1):
            handoff = record_select_handoff(photos, [pick])

        assert handoff is not None
        self.assertTrue(handoff.is_file())
        document = session.load_session("frame", self.root) or {}
        self.assertEqual(document["context"]["handoff"], str(handoff))

    def test_job_results_still_reads_what_survives(self) -> None:
        self.stamps(6)
        prune_manifests(keep=3)

        reports = recent_reports()

        self.assertEqual(len(reports), 3)
        self.assertTrue(all(report.manifest_path.is_file() for report in reports))


if __name__ == "__main__":
    unittest.main()
