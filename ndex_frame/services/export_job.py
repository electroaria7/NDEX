"""Immutable export planning and sequential, failure-isolated execution."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Literal

from ndex_frame.core.geometry import build_render_plan, resolve_canvas
from ndex_frame.core.models import FramePreset, ImageOverride, OutputProfile, RenderPlan, SourceItem
from ndex_frame.core.validation import validate_output_directory
from ndex_frame.imaging.color import prepare_master
from ndex_frame.imaging.encoders import save_output_atomic
from ndex_frame.imaging.renderer import render

CollisionPolicy = Literal["skip", "rename"]
PlanAction = Literal["export", "skip", "error"]
ProgressState = Literal["started", "exported", "skipped", "failed", "cancelled"]

_EXTENSIONS = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}


@dataclass(frozen=True, slots=True)
class ExportRequest:
    sources: tuple[SourceItem, ...]
    output_dir: Path
    frame: FramePreset
    output: OutputProfile
    overrides: tuple[ImageOverride, ...]
    collision_policy: CollisionPolicy


@dataclass(frozen=True, slots=True)
class ExportItemPlan:
    source: SourceItem
    destination: Path
    render_plan: RenderPlan
    action: PlanAction
    message: str = ""


@dataclass(frozen=True, slots=True)
class ExportJobSnapshot:
    output_dir: Path
    frame: FramePreset
    output: OutputProfile
    items: tuple[ExportItemPlan, ...]


@dataclass(frozen=True, slots=True)
class ExportProgress:
    index: int
    total: int
    source: Path
    state: ProgressState
    message: str = ""


@dataclass(frozen=True, slots=True)
class ExportItemResult:
    source: Path
    destination: Path
    state: Literal["exported", "skipped", "failed"]
    message: str = ""


@dataclass(frozen=True, slots=True)
class ExportResult:
    exported: int
    skipped: int
    failed: int
    cancelled: bool
    items: tuple[ExportItemResult, ...]


class CancelToken:
    """Thread-safe cooperative cancellation flag checked between files."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


def _notify_progress(progress: Callable[[ExportProgress], None], event: ExportProgress) -> None:
    """Notify a best-effort observer without letting it change export results."""
    try:
        progress(event)
    except Exception:
        # Progress is observational: an ordinary UI/adapter callback failure
        # must not reclassify completed work or stop subsequent items.
        pass


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _reserved_key(path: Path) -> str:
    return os.path.normcase(path.name)


def _renamed_destination(base: Path, sequence: int) -> Path:
    return base.with_name(f"{base.stem}_{sequence:02d}{base.suffix}")


def plan_export(request: ExportRequest) -> ExportJobSnapshot:
    """Validate and freeze a complete job without creating final outputs."""
    if request.collision_policy not in ("skip", "rename"):
        raise ValueError(f"Unsupported collision policy: {request.collision_policy}")

    output_dir = validate_output_directory(request.output_dir)
    canvas_size = resolve_canvas(request.output.sizing, request.frame.ratio)
    overrides: dict[str, ImageOverride] = {}
    for override in request.overrides:
        key = _path_key(override.source_path)
        if key in overrides:
            raise ValueError(f"Duplicate override for source: {override.source_path}")
        overrides[key] = override

    existing = {_reserved_key(path) for path in output_dir.iterdir()}
    reserved = set(existing)
    items: list[ExportItemPlan] = []
    extension = _EXTENSIONS[request.output.format]

    for source in request.sources:
        destination = output_dir / f"{source.path.stem}{extension}"
        key = _reserved_key(destination)
        action: PlanAction = "export"
        message = ""

        if key in reserved:
            if request.collision_policy == "skip":
                action = "skip"
                message = "Destination already exists or is reserved by this batch."
            else:
                sequence = 1
                while True:
                    candidate = _renamed_destination(destination, sequence)
                    if _reserved_key(candidate) not in reserved:
                        destination = candidate
                        key = _reserved_key(candidate)
                        break
                    sequence += 1

        override = overrides.get(_path_key(source.path))
        try:
            render_plan = build_render_plan(
                (source.oriented_width, source.oriented_height),
                canvas_size,
                override.photo_scale if override else request.frame.photo_scale,
                override.x if override else request.frame.x,
                override.y if override else request.frame.y,
            )
        except Exception as error:
            render_plan = RenderPlan(canvas_size[0], canvas_size[1], 0, 0, 0, 0)
            action = "error"
            message = str(error)

        if action == "export":
            reserved.add(key)
        items.append(ExportItemPlan(source, destination, render_plan, action, message))

    return ExportJobSnapshot(output_dir, request.frame, request.output, tuple(items))


def run_export(
    snapshot: ExportJobSnapshot,
    progress: Callable[[ExportProgress], None],
    cancel: CancelToken,
) -> ExportResult:
    """Run planned items sequentially while isolating ordinary per-file failures."""
    results: list[ExportItemResult] = []
    total = len(snapshot.items)
    cancelled = False

    for index, item in enumerate(snapshot.items, start=1):
        if cancel.is_cancelled():
            cancelled = True
            _notify_progress(
                progress, ExportProgress(index, total, item.source.path, "cancelled", "Export cancelled.")
            )
            break

        if item.action == "skip":
            results.append(ExportItemResult(item.source.path, item.destination, "skipped", item.message))
            _notify_progress(progress, ExportProgress(index, total, item.source.path, "skipped", item.message))
            continue
        if item.action == "error":
            results.append(ExportItemResult(item.source.path, item.destination, "failed", item.message))
            _notify_progress(progress, ExportProgress(index, total, item.source.path, "failed", item.message))
            continue

        _notify_progress(progress, ExportProgress(index, total, item.source.path, "started"))
        prepared = None
        rendered = None
        try:
            prepared = prepare_master(item.source.path, snapshot.output.metadata)
            rendered = render(prepared, item.render_plan, snapshot.frame.background)
            save_output_atomic(rendered, item.destination, snapshot.output, prepared)
            results.append(ExportItemResult(item.source.path, item.destination, "exported"))
            _notify_progress(progress, ExportProgress(index, total, item.source.path, "exported"))
        except Exception as error:
            message = str(error) or error.__class__.__name__
            results.append(ExportItemResult(item.source.path, item.destination, "failed", message))
            _notify_progress(progress, ExportProgress(index, total, item.source.path, "failed", message))
        finally:
            if rendered is not None:
                rendered.close()
            if prepared is not None:
                prepared.image.close()

    return ExportResult(
        exported=sum(item.state == "exported" for item in results),
        skipped=sum(item.state == "skipped" for item in results),
        failed=sum(item.state == "failed" for item in results),
        cancelled=cancelled,
        items=tuple(results),
    )
