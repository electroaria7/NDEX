"""Record a finished job: write a manifest and update the app session."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from ndex_common import manifest, session


def record_job(
    *,
    app: str,
    type: str,
    source: str = "",
    destination: str = "",
    counts: Mapping[str, int] | None = None,
    items: Iterable[Mapping[str, Any]] | None = None,
    folders: Mapping[str, str] | None = None,
    context: Mapping[str, Any] | None = None,
) -> Path | None:
    try:
        path = manifest.write_manifest(
            type=type,
            app=app,
            source=source,
            destination=destination,
            counts=counts,
            items=items,
            context=context,
        )
    except OSError:
        return None

    # The manifest is the record of the job. Updating the session is a
    # convenience on top of it, so a failure there still returns the manifest.
    try:
        extra = dict(context or {})
        extra.pop("files", None)
        extra["counts"] = dict(counts or {})
        if type == "select_handoff":
            extra["handoff"] = str(path)
        session.remember(
            app,
            folders=dict(folders or {}),
            last_manifest=str(path),
            context=extra,
        )
        if type == "select_handoff":
            session.remember(
                "frame",
                folders={"source": source} if source else {},
                last_manifest=str(path),
                context={"handoff": str(path)},
            )
    except OSError:
        pass
    return path


def record_extract(
    selected_jpg: Path | str,
    raw_source: Path | str,
    work_folder: Path | str,
    result: Any,
) -> Path | None:
    counts = {
        "copied": int(getattr(result, "copied", 0)),
        "skipped": int(getattr(result, "skipped", 0)),
        "ambiguous": int(getattr(result, "ambiguous", 0)),
        "missing": int(getattr(result, "missing", 0)),
        "failed": int(getattr(result, "errors", 0)),
    }
    return record_job(
        app="auto_selector",
        type="extract",
        source=str(selected_jpg),
        destination=str(work_folder),
        counts=counts,
        items=getattr(result, "items", ()) or (),
        folders={
            "selected_jpg": str(selected_jpg),
            "raw_source": str(raw_source),
            "work": str(work_folder),
        },
    )


def record_export(
    source: Path | str,
    destination: Path | str,
    result: Any,
    *,
    frame_preset: str = "",
    output_profile: str = "",
) -> Path | None:
    items = [
        {
            "path": str(getattr(item, "source", "")),
            "destination": str(getattr(item, "destination", "")),
            "status": str(getattr(item, "state", "")),
            "detail": str(getattr(item, "message", "")),
        }
        for item in getattr(result, "items", ()) or ()
    ]
    counts = {
        "copied": int(getattr(result, "exported", 0)),
        "skipped": int(getattr(result, "skipped", 0)),
        "failed": int(getattr(result, "failed", 0)),
    }
    return record_job(
        app="frame",
        type="export",
        source=str(source),
        destination=str(destination),
        counts=counts,
        items=items,
        folders={"source": str(source), "output": str(destination)},
        context={
            "frame_preset": frame_preset,
            "output_profile": output_profile,
            "cancelled": bool(getattr(result, "cancelled", False)),
        },
    )


def record_select_handoff(
    source_folder: Path | str,
    files: Iterable[Path | str],
) -> Path | None:
    paths = [str(path) for path in files]
    items = [{"path": path, "status": "selected"} for path in paths]
    return record_job(
        app="image_manager",
        type="select_handoff",
        source=str(source_folder),
        counts={"selected": len(paths)},
        items=items,
        folders={"source": str(source_folder)},
        context={"files": paths},
    )


def record_backup(source: Path | str, destination: Path | str, result: Any) -> Path | None:
    counts = {
        "copied": int(getattr(result, "copied", 0)),
        "skipped": int(getattr(result, "skipped", 0)),
        "failed": int(getattr(result, "errors", 0)),
        "overwritten": int(getattr(result, "overwritten", 0)),
    }
    items = list(getattr(result, "items", ()) or ())
    if not items:
        items = [
            {"path": "", "status": "message", "detail": message}
            for message in getattr(result, "messages", [])[:50]
        ]
    return record_job(
        app="ndex_one",
        type="backup",
        source=str(source),
        destination=str(destination),
        counts=counts,
        items=items,
        folders={"source": str(source), "destination": str(destination)},
        context={"cancelled": bool(getattr(result, "cancelled", False))},
    )
