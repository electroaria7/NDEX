from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ndex_common.report import JobItem, JobReport
from ndex_common.retry import plan_retry
from src.gui import DSBApp


def _report(root: Path, failed: Path) -> JobReport:
    return JobReport(
        manifest_path=root / "backup-20260902T101500Z.json",
        type="backup",
        app="ndex_one",
        created_at="2026-09-02T10:15:00Z",
        source=str(root / "card"),
        destination=str(root / "library"),
        counts={"copied": 2, "failed": 1},
        items=(JobItem(path=str(failed), status="failed", detail="disk full"),),
        context={},
    )


class RecordBackupSessionTests(unittest.TestCase):
    """A finished backup is recorded against the job it was started as."""

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.failed = self.root / "IMG_0001.CR3"
        self.failed.write_bytes(b"raw")
        self.result = SimpleNamespace(copied=1, skipped=0, errors=0)

    def _window(self, job: dict) -> SimpleNamespace:
        return SimpleNamespace(pending_backup=job)

    def test_an_ordinary_backup_is_recorded_against_the_analysed_folders(self) -> None:
        job = {"source": "E:/CARD", "destination": "D:/Analysed", "retry": None}
        with patch("ndex_common.workflow.record_backup") as record:
            DSBApp._record_backup_session(self._window(job), self.result)

        # Not the form: it can have changed since Analyze ran.
        record.assert_called_once_with("E:/CARD", "D:/Analysed", self.result, context=None)

    def test_a_retry_is_recorded_against_the_job_it_came_from(self) -> None:
        report = _report(self.root, self.failed)
        plan = plan_retry(report)
        job = {"source": report.source, "destination": report.destination, "retry": plan}
        with patch("ndex_common.workflow.record_backup") as record:
            DSBApp._record_backup_session(self._window(job), self.result)

        record.assert_called_once()
        source, destination, result = record.call_args.args
        self.assertEqual(source, report.source)
        self.assertEqual(destination, report.destination)
        self.assertIs(result, self.result)
        context = record.call_args.kwargs["context"]
        self.assertEqual(context["retry_of"], str(report.manifest_path))
        self.assertEqual(context["retried"], 1)


if __name__ == "__main__":
    unittest.main()
