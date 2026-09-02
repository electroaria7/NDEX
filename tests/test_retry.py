from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ndex_common import retry
from ndex_common.report import JobItem, JobReport


def _report(**overrides) -> JobReport:
    fields = {
        "manifest_path": Path("backup-20260902T101500Z.json"),
        "type": "backup",
        "app": "ndex_one",
        "created_at": "2026-09-02T10:15:00Z",
        "source": "",
        "destination": "",
        "counts": {"copied": 2, "failed": 1},
        "items": (),
        "context": {},
    }
    fields.update(overrides)
    return JobReport(**fields)


class SupportsRetryTests(unittest.TestCase):
    def test_the_three_running_apps_can_retry_their_own_job_type(self) -> None:
        self.assertTrue(retry.supports_retry(_report()))
        self.assertTrue(retry.supports_retry(_report(app="auto_selector", type="extract")))
        self.assertTrue(retry.supports_retry(_report(app="frame", type="export")))

    def test_a_select_handoff_is_not_work_to_rerun(self) -> None:
        handoff = _report(app="image_manager", type="select_handoff")
        self.assertFalse(retry.supports_retry(handoff))
        self.assertFalse(retry.plan_retry(handoff).ready)

    def test_a_job_type_the_app_does_not_run_is_not_retryable(self) -> None:
        self.assertFalse(retry.supports_retry(_report(app="frame", type="backup")))


class PlanRetryTests(unittest.TestCase):
    def test_splits_problems_into_present_and_gone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            here = Path(tmp) / "a.CR3"
            here.write_bytes(b"raw")
            gone = Path(tmp) / "b.CR3"
            plan = retry.plan_retry(
                _report(
                    items=(
                        JobItem(path=str(here), status="failed"),
                        JobItem(path=str(gone), status="failed"),
                        JobItem(path=str(here.with_name("c.CR3")), status="copied"),
                    )
                )
            )

        self.assertEqual(plan.paths, (here,))
        self.assertEqual(plan.missing, (gone,))
        self.assertTrue(plan.ready)

    def test_ambiguous_and_missing_count_as_problems_worth_retrying(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.jpg"
            first.write_bytes(b"jpg")
            second = Path(tmp) / "b.jpg"
            second.write_bytes(b"jpg")
            plan = retry.plan_retry(
                _report(
                    app="auto_selector",
                    type="extract",
                    items=(
                        JobItem(path=str(first), status="ambiguous"),
                        JobItem(path=str(second), status="missing"),
                    ),
                )
            )

        self.assertEqual(len(plan.paths), 2)

    def test_the_same_file_listed_twice_is_retried_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.CR3"
            path.write_bytes(b"raw")
            plan = retry.plan_retry(
                _report(
                    items=(
                        JobItem(path=str(path), status="failed"),
                        JobItem(path=str(path), status="failed"),
                    )
                )
            )

        self.assertEqual(plan.paths, (path,))

    def test_a_clean_job_has_nothing_to_retry(self) -> None:
        plan = retry.plan_retry(_report(items=(JobItem(path="a.CR3", status="copied"),)))
        self.assertFalse(plan.ready)
        self.assertIn("no failed items", plan.summary)

    def test_summary_counts_what_runs_and_what_is_left_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            here = Path(tmp) / "a.CR3"
            here.write_bytes(b"raw")
            plan = retry.plan_retry(
                _report(
                    items=(
                        JobItem(path=str(here), status="failed"),
                        JobItem(path=str(Path(tmp) / "gone.CR3"), status="failed"),
                    )
                )
            )

        self.assertIn("Retry 1 file(s)", plan.summary)
        self.assertIn("1 more are no longer on disk", plan.summary)

    def test_summary_says_so_when_every_problem_file_is_gone(self) -> None:
        plan = retry.plan_retry(
            _report(items=(JobItem(path="Z:/gone/a.CR3", status="failed"),))
        )
        self.assertFalse(plan.ready)
        self.assertIn("nothing to retry", plan.summary)


class RetryContextTests(unittest.TestCase):
    def test_context_points_back_at_the_job_being_retried(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.CR3"
            path.write_bytes(b"raw")
            report = _report(
                manifest_path=Path(tmp) / "backup-20260902T101500Z.json",
                items=(JobItem(path=str(path), status="failed"),),
            )
            context = retry.plan_retry(report).context()

        self.assertEqual(context["retry_of"], str(report.manifest_path))
        self.assertEqual(context["retry_of_created_at"], "2026-09-02T10:15:00Z")
        self.assertEqual(context["retried"], 1)

    def test_is_retry_reads_that_marker_back(self) -> None:
        self.assertFalse(retry.is_retry(_report()))
        self.assertTrue(retry.is_retry(_report(context={"retry_of": "backup-1.json"})))

class RetryQuestionTests(unittest.TestCase):
    def _plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.CR3"
            path.write_bytes(b"raw")
            return retry.plan_retry(
                _report(
                    source="E:/DCIM",
                    destination="D:/Lib",
                    items=(JobItem(path=str(path), status="failed"),),
                )
            )

    def test_question_names_both_folders_and_the_settings_rule(self) -> None:
        question = self._plan().question()
        self.assertIn("Retry 1 file(s).", question)
        self.assertIn("Source: E:/DCIM", question)
        self.assertIn("Destination: D:/Lib", question)
        self.assertIn("settings showing in the main window", question)
        self.assertTrue(question.endswith("Continue?"))

    def test_apps_can_relabel_the_destination_and_add_a_note(self) -> None:
        question = self._plan().question(destination_label="Output", note="Frame opens just these files.")
        self.assertIn("Output: D:/Lib", question)
        self.assertNotIn("Destination:", question)
        self.assertIn("Frame opens just these files.", question)


class RetryableTests(unittest.TestCase):
    def test_retryable_reads_only_the_manifest(self) -> None:
        # A gone file is still "retryable" here; plan_retry is what checks the disk.
        gone = _report(items=(JobItem(path="Z:/gone/a.CR3", status="failed"),))
        self.assertTrue(retry.retryable(gone))
        self.assertFalse(retry.plan_retry(gone).ready)

    def test_a_clean_job_is_not_retryable(self) -> None:
        self.assertFalse(retry.retryable(_report(items=(JobItem(path="a.CR3", status="copied"),))))



if __name__ == "__main__":
    unittest.main()
