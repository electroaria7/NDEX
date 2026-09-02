"""Workflow session state for the NDEX Launcher.

Reads explicit session documents (and legacy last-folder keys) to show where
the user left off, and builds Continue handoff arguments. Missing folders
fall back to Open Empty (``--open`` only). Each step also carries the most
recent finished job for that app, read back from its manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ndex_common import session as workflow_session
from ndex_common.report import JobReport, latest_reports_by_app
from ndex_common.settings import load_all


@dataclass(slots=True)
class StepState:
    key: str
    title: str
    description: str
    last_folder: str = ""
    launch_args: list[str] = field(default_factory=list)
    number: str = ""
    short_title: str = ""
    last_manifest: str = ""
    handoff_ready: bool = False
    last_result: JobReport | None = None

    @property
    def result_text(self) -> str:
        """What the app's most recent finished job did, for the card."""
        if self.last_result is None:
            return "No job results yet"
        return self.last_result.headline

    @property
    def has_session(self) -> bool:
        return self.launch_args != ["--open"]

    @property
    def status_text(self) -> str:
        folder_ready = bool(self.last_folder) and Path(self.last_folder).is_dir()
        if self.handoff_ready and not folder_ready:
            return f"Last handoff: {self.last_manifest}"
        if not self.last_folder:
            return "No previous session"
        if not folder_ready:
            return f"Last folder missing: {self.last_folder}"
        return f"Last: {self.last_folder}"


def gather_workflow_state() -> list[StepState]:
    data = load_all()
    documents = workflow_session.latest_from_settings(data)

    steps = [
        StepState(
            key="ndex_one",
            title="1. Backup - NDEX One",
            short_title="Backup",
            number="01",
            description="Copy camera or SD files into the date-based library.",
        ),
        StepState(
            key="image_manager",
            title="2. Select & Rate - Image Manager",
            short_title="Select & Rate",
            number="02",
            description="Browse pairs, pick, rate, and export XMP sidecars.",
        ),
        StepState(
            key="auto_selector",
            title="3. Extract - Auto Selector",
            short_title="Extract",
            number="03",
            description="Match selected JPGs to RAW masters and write XMP.",
        ),
        StepState(
            key="frame",
            title="4. Frame & Export - NDEX Frame",
            short_title="Frame & Export",
            number="04",
            description="Place masters on a crop-free canvas for Instagram.",
        ),
    ]

    results = _latest_result_by_app([step.key for step in steps])

    for step in steps:
        document = documents[step.key]
        step.last_result = results.get(step.key)
        step.last_folder = workflow_session.preferred_folder(document)
        handoff = workflow_session.usable_handoff(document)
        step.handoff_ready = bool(handoff)
        step.last_manifest = handoff or str(document.get("last_manifest") or "")
        step.launch_args = workflow_session.launch_args(document)
    return steps


def _latest_result_by_app(apps: list[str]) -> dict[str, JobReport]:
    """Newest finished job per app. Missing manifests are simply absent."""
    return latest_reports_by_app(apps)
