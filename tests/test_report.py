from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common import report


def _write(root: Path, name: str, payload: dict) -> Path:
    folder = root / "manifests"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _manifest(
    *,
    type: str = "backup",
    app: str = "ndex_one",
    created_at: str = "2026-09-02T10:15:00Z",
    counts: dict | None = None,
    items: list | None = None,
    source: str = "",
    destination: str = "",
    context: dict | None = None,
) -> dict:
    return {
        "kind": "ndex.manifest",
        "schema_version": 1,
        "type": type,
        "app": app,
        "created_at": created_at,
        "source": source,
        "destination": destination,
        "counts": counts or {},
        "items": items or [],
        "context": context or {},
    }


class JobReportTests(unittest.TestCase):
    def test_reads_counts_and_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write(
                root,
                "backup-20260902T101500Z.json",
                _manifest(
                    counts={"copied": 42, "skipped": 3, "failed": 1},
                    items=[
                        {"path": "a.CR3", "status": "copied"},
                        {"path": "b.CR3", "status": "failed", "detail": "disk full"},
                    ],
                    source="E:/DCIM",
                    destination="D:/Lib",
                ),
            )
            found = report.read_report(path)

        assert found is not None
        self.assertEqual(found.type_label, "Backup")
        self.assertEqual(found.app_label, "NDEX One")
        self.assertEqual(found.count_summary, "42 copied, 3 skipped, 1 failed")
        self.assertEqual(found.failed_count, 1)
        self.assertEqual(found.problem_paths(), ["b.CR3"])
        self.assertEqual(found.problems[0].detail, "disk full")

    def test_count_summary_omits_zero_and_unknown_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(
                Path(tmp),
                "export-20260902T101500Z.json",
                _manifest(type="export", app="frame", counts={"copied": 5, "skipped": 0, "failed": 0}),
            )
            found = report.read_report(path)

        assert found is not None
        self.assertEqual(found.count_summary, "5 copied")

    def test_empty_counts_say_nothing_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "backup-20260902T101500Z.json", _manifest())
            found = report.read_report(path)

        assert found is not None
        self.assertEqual(found.count_summary, "nothing recorded")

    def test_items_group_with_problems_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(
                Path(tmp),
                "extract-20260902T101500Z.json",
                _manifest(
                    type="extract",
                    app="auto_selector",
                    items=[
                        {"path": "a.CR3", "status": "copied"},
                        {"path": "b.CR3", "status": "ambiguous"},
                        {"path": "c.CR3", "status": "copied"},
                        {"path": "d.CR3", "status": "failed"},
                    ],
                ),
            )
            found = report.read_report(path)

        assert found is not None
        grouped = found.items_by_status()
        self.assertEqual(list(grouped)[:2], ["ambiguous", "failed"])
        self.assertEqual(len(grouped["copied"]), 2)

    def test_failed_count_falls_back_to_counting_problem_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(
                Path(tmp),
                "extract-20260902T101500Z.json",
                _manifest(
                    type="extract",
                    app="auto_selector",
                    counts={"copied": 2},
                    items=[
                        {"path": "a.CR3", "status": "copied"},
                        {"path": "b.CR3", "status": "missing"},
                    ],
                ),
            )
            found = report.read_report(path)

        assert found is not None
        self.assertEqual(found.failed_count, 1)

    def test_cancelled_job_is_marked_in_the_headline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(
                Path(tmp),
                "backup-20260902T101500Z.json",
                _manifest(counts={"copied": 4}, context={"cancelled": True}),
            )
            found = report.read_report(path)

        assert found is not None
        self.assertTrue(found.cancelled)
        self.assertTrue(found.headline.endswith("(cancelled)"))

    def test_unreadable_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = _write(root, "backup-20260902T101500Z.json", {"nope": True})
            self.assertIsNone(report.read_report(broken))
            self.assertIsNone(report.read_report(root / "manifests" / "absent.json"))

    def test_unparsable_timestamp_is_shown_as_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(
                Path(tmp), "backup-20260902T101500Z.json", _manifest(created_at="whenever")
            )
            found = report.read_report(path)

        assert found is not None
        self.assertEqual(found.display_time, "whenever")


class RecentReportTests(unittest.TestCase):
    def test_newest_first_and_latest_pointers_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "backup-20260901T090000Z.json", _manifest(created_at="2026-09-01T09:00:00Z"))
            _write(root, "backup-20260902T101500Z.json", _manifest(created_at="2026-09-02T10:15:00Z"))
            _write(root, "latest-ndex_one-backup.json", _manifest(created_at="2026-09-02T10:15:00Z"))
            found = report.recent_reports(root=root)

        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].created_at, "2026-09-02T10:15:00Z")

    def test_filters_by_app_and_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "backup-20260901T090000Z.json", _manifest())
            _write(
                root,
                "export-20260902T101500Z.json",
                _manifest(type="export", app="frame", created_at="2026-09-02T10:15:00Z"),
            )
            _write(
                root,
                "select_handoff-20260902T110000Z.json",
                _manifest(type="select_handoff", app="image_manager", created_at="2026-09-02T11:00:00Z"),
            )

            frames = report.recent_reports(root=root, apps=("frame",))
            handoffs = report.recent_reports(root=root, types=("select_handoff",))

        self.assertEqual([found.app for found in frames], ["frame"])
        self.assertEqual([found.type for found in handoffs], ["select_handoff"])

    def test_limit_zero_returns_everything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for hour in range(5):
                _write(
                    root,
                    f"backup-20260902T0{hour}0000Z.json",
                    _manifest(created_at=f"2026-09-02T0{hour}:00:00Z"),
                )
            self.assertEqual(len(report.recent_reports(root=root, limit=2)), 2)
            self.assertEqual(len(report.recent_reports(root=root, limit=0)), 5)

    def test_missing_manifest_folder_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(report.recent_reports(root=Path(tmp)), [])

    def test_latest_report_reads_the_pointer_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "latest-frame-export.json", _manifest(type="export", app="frame"))
            found = report.latest_report("frame", "export", root=root)

        assert found is not None
        self.assertEqual(found.app, "frame")

    def test_latest_report_rejects_unknown_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                report.latest_report("frame", "nope", root=Path(tmp))

class LatestByAppTests(unittest.TestCase):
    def test_newest_job_per_app_without_reading_older_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "backup-20260901T090000Z.json", _manifest(created_at="2026-09-01T09:00:00Z"))
            _write(root, "backup-20260902T101500Z.json", _manifest(created_at="2026-09-02T10:15:00Z"))
            _write(
                root,
                "export-20260902T110000Z.json",
                _manifest(type="export", app="frame", created_at="2026-09-02T11:00:00Z"),
            )
            with patch.object(report, "read_report", wraps=report.read_report) as read:
                latest = report.latest_reports_by_app(("ndex_one", "frame"), root=root)

        self.assertEqual(latest["ndex_one"].created_at, "2026-09-02T10:15:00Z")
        self.assertEqual(latest["frame"].app, "frame")
        # Stopped once both apps were seen: the oldest backup was never parsed.
        self.assertEqual(read.call_count, 2)

    def test_apps_with_no_jobs_are_simply_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            latest = report.latest_reports_by_app(("ndex_one",), root=Path(tmp))
        self.assertEqual(latest, {})

    def test_recent_reports_stops_reading_at_the_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for hour in range(5):
                _write(
                    root,
                    f"backup-20260902T0{hour}0000Z.json",
                    _manifest(created_at=f"2026-09-02T0{hour}:00:00Z"),
                )
            with patch.object(report, "read_report", wraps=report.read_report) as read:
                found = report.recent_reports(root=root, limit=2)

        self.assertEqual([item.created_at for item in found], ["2026-09-02T04:00:00Z", "2026-09-02T03:00:00Z"])
        self.assertEqual(read.call_count, 2)



if __name__ == "__main__":
    unittest.main()
