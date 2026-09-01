"""Workflow session state for the NDEX Launcher.

Reads the shared settings file to show where the user left off in the
backup -> select -> extract -> frame workflow, and builds the handoff
arguments each step should launch with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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

    @property
    def has_session(self) -> bool:
        return bool(self.last_folder) and Path(self.last_folder).is_dir()

    @property
    def status_text(self) -> str:
        if not self.last_folder:
            return "No previous session"
        if not Path(self.last_folder).is_dir():
            return f"Last folder missing: {self.last_folder}"
        return f"Last: {self.last_folder}"


def gather_workflow_state() -> list[StepState]:
    data = load_all()
    image_manager = data.get("image_manager", {}) if isinstance(data.get("image_manager"), dict) else {}
    auto_selector = data.get("auto_selector", {}) if isinstance(data.get("auto_selector"), dict) else {}
    frame = data.get("frame", {}) if isinstance(data.get("frame"), dict) else {}

    backup_destination = str(data.get("last_destination", "") or "")
    manager_source = str(image_manager.get("last_source", "") or "")
    selector_jpg = str(auto_selector.get("last_selected_jpg", "") or "")
    selector_raw = str(auto_selector.get("last_raw_source", "") or "")
    frame_source = str(frame.get("last_source", "") or "")

    steps = [
        StepState(
            key="ndex_one",
            title="1. Backup - NDEX One",
            short_title="Backup",
            number="01",
            description="Copy camera or SD files into the date-based library.",
            last_folder=backup_destination,
        ),
        StepState(
            key="image_manager",
            title="2. Select & Rate - Image Manager",
            short_title="Select & Rate",
            number="02",
            description="Browse pairs, pick, rate, and export XMP sidecars.",
            last_folder=manager_source or backup_destination,
        ),
        StepState(
            key="auto_selector",
            title="3. Extract - Auto Selector",
            short_title="Extract",
            number="03",
            description="Match selected JPGs to RAW masters and write XMP.",
            last_folder=selector_jpg,
        ),
        StepState(
            key="frame",
            title="4. Frame & Export - NDEX Frame",
            short_title="Frame & Export",
            number="04",
            description="Place masters on a crop-free canvas for Instagram.",
            last_folder=frame_source,
        ),
    ]

    steps[1].launch_args = _image_manager_args(steps[1])
    steps[2].launch_args = _auto_selector_args(selector_jpg, selector_raw)
    steps[3].launch_args = _image_manager_args(steps[3])
    return steps


def _image_manager_args(step: StepState) -> list[str]:
    if step.has_session:
        return ["--open", "--source", step.last_folder]
    return ["--open"]


def _auto_selector_args(selected_jpg: str, raw_source: str) -> list[str]:
    args = ["--open"]
    if selected_jpg and Path(selected_jpg).is_dir():
        args.extend(["--selected-jpg", selected_jpg])
    if raw_source and Path(raw_source).is_dir():
        args.extend(["--raw-source", raw_source])
    return args
