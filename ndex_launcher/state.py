"""Workflow session state for the NDEX Launcher.

Reads explicit session documents (and legacy last-folder keys) to show where
the user left off, and builds Continue handoff arguments. Missing folders
fall back to Open Empty (``--open`` only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ndex_common import session as workflow_session
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

    @property
    def has_session(self) -> bool:
        return self.launch_args != ["--open"]

    @property
    def status_text(self) -> str:
        if self.last_manifest and Path(self.last_manifest).is_file() and not self.last_folder:
            return f"Last handoff: {self.last_manifest}"
        if not self.last_folder:
            return "No previous session"
        if not Path(self.last_folder).is_dir():
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

    for step in steps:
        document = documents[step.key]
        step.last_folder = workflow_session.preferred_folder(document)
        step.last_manifest = str(document.get("last_manifest") or "")
        if not step.last_manifest:
            step.last_manifest = str((document.get("context") or {}).get("handoff") or "")
        step.launch_args = workflow_session.launch_args(document)
    return steps
