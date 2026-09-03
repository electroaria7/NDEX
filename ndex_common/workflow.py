"""Record a finished job: write a manifest and update the app session."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from ndex_common import manifest, retention, session

# Per-file records a manifest keeps for statuses that went fine. Problems are
# always kept in full: they are what a retry reads. Totals live in counts.
KEEP_PER_STATUS = 500
PROBLEM_STATUSES = frozenset({"failed", "error", "ambiguous", "missing"})


def trim_items(items: Iterable[Mapping[str, Any]], keep: int = KEEP_PER_STATUS) -> list[dict[str, Any]]:
    """Cap the per-file records of each untroubled status.

    A card backup can reach tens of thousands of files, and every one of
    them would otherwise be written twice and parsed on every open of Job
    Results. The first ``keep`` of each status stay, and one closing record
    says how many more there were.
    """
    kept: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for item in items:
        entry = dict(item)
        status = str(entry.get("status") or "unknown")
        if status.casefold() in PROBLEM_STATUSES:
            kept.append(entry)
            continue
        seen[status] = seen.get(status, 0) + 1
        if seen[status] <= keep:
            kept.append(entry)
    for status, total in seen.items():
        if total > keep:
            kept.append({"path": "", "status": status, "detail": f"+{total - keep} more not listed"})
    return kept


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
            items=trim_items(items or ()),
            context=context,
            folders=folders,
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

    # Now that the sessions point where they should, drop the manifests
    # nothing points at any more. After the session update, so a manifest
    # this job just pinned is never a candidate.
    retention.prune_manifests()
    return path


def record_extract(
    selected_jpg: Path | str,
    raw_source: Path | str,
    work_folder: Path | str,
    result: Any,
    *,
    recursive: bool | None = None,
    context: Mapping[str, Any] | None = None,
) -> Path | None:
    """``recursive`` is which folders were searched; a retry searches the same."""
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
        context={
            **({"recursive": bool(recursive)} if recursive is not None else {}),
            **dict(context or {}),
        },
    )


def record_export(
    source: Path | str,
    destination: Path | str,
    result: Any,
    *,
    frame_preset: str = "",
    output_profile: str = "",
    context: Mapping[str, Any] | None = None,
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
    # "exported", not "copied": it is the status the items themselves carry,
    # and an export writes a new file rather than copying one.
    counts = {
        "exported": int(getattr(result, "exported", 0)),
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
            **dict(context or {}),
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


def record_backup(
    source: Path | str,
    destination: Path | str,
    result: Any,
    *,
    context: Mapping[str, Any] | None = None,
) -> Path | None:
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
        context={
            "cancelled": bool(getattr(result, "cancelled", False)),
            **dict(context or {}),
        },
    )
