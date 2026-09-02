"""Work out which files of a finished job can still be retried.

A job manifest records the files that failed, went missing, or matched
ambiguously. Retrying means running those files again — but a manifest is a
record of the past, and the photographs it names may have been moved,
renamed, or deleted since. This module is the part that checks.

It decides *what* to retry. Running the files is the owning app's job:
NDEX One re-backs up, Auto Selector re-extracts, Frame re-exports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ndex_common.report import JobReport, path_key, same_path

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

    def question(self, *, destination_label: str = "Destination", note: str = "") -> str:
        """The confirmation every app shows before a retry starts.

        One text for all of them, so the promise about folders and settings
        reads the same wherever the button lives.
        """
        lines = [self.summary, ""]
        if self.report.source:
            lines.append(f"Source: {self.report.source}")
        if self.report.destination:
            lines.append(f"{destination_label}: {self.report.destination}")
        lines.append("")
        if note:
            lines.append(note)
        lines.append("They run again with the settings showing in the main window.")
        lines.append("")
        lines.append("Continue?")
        return chr(10).join(lines)

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


def retryable(report: JobReport) -> bool:
    """True when the job has problem files an app could run again.

    This only reads the manifest. Whether the files are still on disk is
    ``plan_retry``'s question, and that one touches the filesystem, so a
    results list asks this first and plans only when the button is pressed.
    """
    return supports_retry(report) and bool(report.problem_paths())


def plan_retry(report: JobReport) -> RetryPlan:
    """Split the job's problem files into retryable ones and ones that are gone.

    Stats every problem path, so call it on demand rather than per selection:
    a manifest can point at a card that has since been unplugged.
    """
    if not supports_retry(report):
        return RetryPlan(report)

    paths: list[Path] = []
    missing: list[Path] = []
    seen: set[str] = set()
    # A folder that is gone takes all its files with it. One stat answers
    # for every file in it, which matters when the folder was a card since
    # unplugged or a share since disconnected: each stat there can hang.
    folder_present: dict[str, bool] = {}
    for raw in report.problem_paths():
        path = Path(raw)
        key = path_key(path)
        if key in seen:
            continue
        seen.add(key)
        folder = path_key(path.parent)
        if folder not in folder_present:
            folder_present[folder] = path.parent.is_dir()
        present = folder_present[folder] and path.is_file()
        (paths if present else missing).append(path)
    return RetryPlan(report, tuple(paths), tuple(missing))


__all__ = [
    "RETRYABLE",
    "RetryPlan",
    "path_key",
    "plan_retry",
    "retryable",
    "same_path",
    "supports_retry",
]
