"""Work out which files of a finished job can still be retried.

A job manifest records the files that failed, went missing, or matched
ambiguously. Retrying means running those files again — but a manifest is a
record of the past, and the photographs it names may have been moved,
renamed, or deleted since. This module is the part that checks.

It decides *what* to retry. Running the files is the owning app's job:
NDEX One re-backs up, Auto Selector re-extracts, Frame re-exports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ndex_common.report import JobReport

# The job type each app can run again. A Select handoff is a pointer, not
# work, so there is nothing to retry.
RETRYABLE = {
    "ndex_one": "backup",
    "auto_selector": "extract",
    "frame": "export",
}


@dataclass(frozen=True)
class RetryPlan:
    """The problem files of one job, split by whether they are still there."""

    report: JobReport
    paths: tuple[Path, ...] = ()
    missing: tuple[Path, ...] = ()

    @property
    def ready(self) -> bool:
        """True when there is at least one file worth running again."""
        return bool(self.paths)

    @property
    def summary(self) -> str:
        """One line explaining what a retry would do, or why it would not."""
        if not self.paths and not self.missing:
            return "This job has no failed items to retry."
        if not self.paths:
            return (
                f"None of the {len(self.missing)} problem file(s) are still where "
                "the job found them, so there is nothing to retry."
            )
        text = f"Retry {len(self.paths)} file(s)."
        if self.missing:
            text += (
                f" {len(self.missing)} more are no longer on disk and will be left out."
            )
        return text

    def context(self) -> dict[str, Any]:
        """Manifest context marking the new job as a retry of the old one."""
        return {
            "retry_of": str(self.report.manifest_path),
            "retry_of_created_at": self.report.created_at,
            "retried": len(self.paths),
        }


def supports_retry(report: JobReport) -> bool:
    """True when the app that ran this job can run its problem files again."""
    return RETRYABLE.get(report.app) == report.type


def plan_retry(report: JobReport) -> RetryPlan:
    """Split the job's problem files into retryable ones and ones that are gone."""
    if not supports_retry(report):
        return RetryPlan(report)

    paths: list[Path] = []
    missing: list[Path] = []
    seen: set[str] = set()
    for raw in report.problem_paths():
        path = Path(raw)
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        (paths if path.is_file() else missing).append(path)
    return RetryPlan(report, tuple(paths), tuple(missing))


def is_retry(report: JobReport) -> bool:
    """True when this job was itself a retry of an earlier one."""
    return bool(report.context.get("retry_of"))


__all__ = ["RETRYABLE", "RetryPlan", "is_retry", "plan_retry", "supports_retry"]
