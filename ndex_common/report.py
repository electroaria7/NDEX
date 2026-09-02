"""Read job manifests back so the apps can show what a job actually did.

Phase 2 writes manifests under ``%LOCALAPPDATA%/NDEX/manifests/``. This module
is the read side: it finds them, summarizes them, and groups their items by
status. Nothing here touches photographs or rewrites a manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from ndex_common.manifest import TYPES, load_manifest, manifests_dir

TYPE_LABELS = {
    "backup": "Backup",
    "extract": "Extract",
    "export": "Export",
    "select_handoff": "Send to Frame",
}

APP_LABELS = {
    "ndex_one": "NDEX One",
    "image_manager": "Image Manager",
    "auto_selector": "Auto Selector",
    "frame": "NDEX Frame",
}

# Counts worth showing, in the order a reader cares about them.
COUNT_ORDER = ("copied", "exported", "selected", "overwritten", "skipped", "ambiguous", "missing", "failed")

# Item statuses that mean the file did not make it.
PROBLEM_STATUSES = frozenset({"failed", "error", "ambiguous", "missing"})


@dataclass(frozen=True)
class JobItem:
    path: str
    status: str
    detail: str = ""
    destination: str = ""

    @property
    def is_problem(self) -> bool:
        return self.status.casefold() in PROBLEM_STATUSES


@dataclass(frozen=True)
class JobReport:
    """One manifest, parsed into what a results view needs."""

    manifest_path: Path
    type: str
    app: str
    created_at: str
    source: str = ""
    destination: str = ""
    counts: Mapping[str, int] = field(default_factory=dict)
    items: tuple[JobItem, ...] = ()
    context: Mapping[str, Any] = field(default_factory=dict)

    @property
    def type_label(self) -> str:
        return TYPE_LABELS.get(self.type, self.type)

    @property
    def app_label(self) -> str:
        return APP_LABELS.get(self.app, self.app)

    @property
    def cancelled(self) -> bool:
        return bool(self.context.get("cancelled"))

    @property
    def problems(self) -> tuple[JobItem, ...]:
        return tuple(item for item in self.items if item.is_problem)

    @property
    def failed_count(self) -> int:
        """Problems the manifest counted, falling back to counting items."""
        counted = sum(int(self.counts.get(key, 0)) for key in ("failed", "ambiguous", "missing"))
        return counted or len(self.problems)

    @property
    def display_time(self) -> str:
        """``created_at`` as local time, or the raw value when it will not parse."""
        try:
            stamp = datetime.strptime(self.created_at, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return self.created_at
        local = stamp.replace(tzinfo=timezone.utc).astimezone()
        return local.strftime("%Y-%m-%d %H:%M")

    @property
    def count_summary(self) -> str:
        """``42 copied, 3 skipped, 1 failed`` — only non-zero counts."""
        parts = [
            f"{int(self.counts[key])} {key}"
            for key in COUNT_ORDER
            if int(self.counts.get(key, 0)) > 0
        ]
        if not parts:
            return "nothing recorded"
        return ", ".join(parts)

    @property
    def headline(self) -> str:
        """One line for a card or list row."""
        text = f"{self.type_label} - {self.display_time} - {self.count_summary}"
        if self.cancelled:
            text = f"{text} (cancelled)"
        return text

    def items_by_status(self) -> dict[str, tuple[JobItem, ...]]:
        """Items grouped by status, problems first, then alphabetical."""
        grouped: dict[str, list[JobItem]] = {}
        for item in self.items:
            grouped.setdefault(item.status or "unknown", []).append(item)
        ordered = sorted(
            grouped,
            key=lambda status: (status.casefold() not in PROBLEM_STATUSES, status.casefold()),
        )
        return {status: tuple(grouped[status]) for status in ordered}

    def problem_paths(self) -> list[str]:
        return [item.path for item in self.problems if item.path]


def read_report(path: Path) -> JobReport | None:
    """Parse one manifest file, or None when it is missing or not a manifest."""
    payload = load_manifest(Path(path))
    if payload is None:
        return None
    return _from_payload(Path(path), payload)


def latest_report(app: str, type: str, root: Path | None = None) -> JobReport | None:
    """The ``latest-{app}-{type}.json`` pointer a finished job leaves behind."""
    if type not in TYPES:
        raise ValueError(f"Unknown manifest type: {type}")
    return read_report(manifests_dir(root) / f"latest-{app}-{type}.json")


def recent_reports(
    *,
    root: Path | None = None,
    apps: Iterable[str] | None = None,
    types: Iterable[str] | None = None,
    limit: int = 20,
) -> list[JobReport]:
    """Timestamped manifests, newest first. ``limit=0`` returns all of them."""
    wanted_apps = set(apps) if apps is not None else None
    wanted_types = set(types) if types is not None else None

    reports: list[JobReport] = []
    try:
        candidates = sorted(manifests_dir(root).glob("*.json"))
    except OSError:
        return []
    for candidate in candidates:
        # latest-* files duplicate a timestamped manifest; skip them here.
        if candidate.name.startswith("latest-"):
            continue
        report = read_report(candidate)
        if report is None:
            continue
        if wanted_apps is not None and report.app not in wanted_apps:
            continue
        if wanted_types is not None and report.type not in wanted_types:
            continue
        reports.append(report)

    reports.sort(key=lambda report: (report.created_at, report.manifest_path.name), reverse=True)
    if limit > 0:
        return reports[:limit]
    return reports


def _from_payload(path: Path, payload: Mapping[str, Any]) -> JobReport:
    counts = payload.get("counts")
    counts = {str(key): _as_int(value) for key, value in counts.items()} if isinstance(counts, dict) else {}
    context = payload.get("context")
    context = dict(context) if isinstance(context, dict) else {}
    return JobReport(
        manifest_path=path,
        type=str(payload.get("type") or ""),
        app=str(payload.get("app") or ""),
        created_at=str(payload.get("created_at") or ""),
        source=str(payload.get("source") or ""),
        destination=str(payload.get("destination") or ""),
        counts=counts,
        items=tuple(_read_items(payload.get("items"))),
        context=context,
    )


def _read_items(raw: Any) -> Iterable[JobItem]:
    if not isinstance(raw, (list, tuple)):
        return ()
    items: list[JobItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        items.append(
            JobItem(
                path=str(entry.get("path") or ""),
                status=str(entry.get("status") or "unknown"),
                detail=str(entry.get("detail") or entry.get("message") or ""),
                destination=str(entry.get("destination") or ""),
            )
        )
    return items


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
