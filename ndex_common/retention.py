"""How long finished-job manifests stay in ``%LOCALAPPDATA%/NDEX/manifests``.

Every finished job writes a manifest and nothing ever removed one, so the
folder grew for as long as the apps were used. This trims it: the newest
``KEEP_PER_TYPE`` of each job type stay, and older ones go unless something
still points at them.

Two things point at a manifest, and both are checked before a delete:

- a session's ``last_manifest``, which is what Job Results opens on;
- a session's ``context.handoff``, which is the list Frame imports.

A retry's ``context.retry_of`` names the job it came from, but nothing
resolves that path -- ``retry_of_created_at`` alongside it already says what
a reader needs -- so it does not pin anything.

Grouping uses the type in the file name (``{type}-{stamp}[-n].json``) rather
than the ``app`` field inside, so pruning never has to parse a manifest to
decide it can go. Each type is written by exactly one app, so the two agree.
"""

from __future__ import annotations

from pathlib import Path

from ndex_common import session
from ndex_common.manifest import TYPES, manifests_dir
from ndex_common.report import name_order, path_key

# Manifests kept per job type. Four types, so this bounds the folder at
# 4x this many files. Job Results lists the 20 most recent, and a retry
# reaches back only as far as the job the user picked, so this is well
# clear of what the UI can reach.
KEEP_PER_TYPE = 100


def pinned_paths(root: Path | None = None) -> set[str]:
    """Manifests a session still points at, as :func:`path_key` spellings."""
    documents: list[dict] = []
    for app in session.APPS:
        document = session.load_session(app, root)
        if document is not None:
            documents.append(document)
    try:
        # The settings snapshot covers a wiped sessions folder.
        documents.extend(session.latest_from_settings().values())
    except OSError:
        pass

    pinned: set[str] = set()
    for document in documents:
        candidates = [
            str(document.get("last_manifest") or ""),
            str((document.get("context") or {}).get("handoff") or ""),
        ]
        pinned.update(path_key(value) for value in candidates if value)
    return pinned


def prune_manifests(*, root: Path | None = None, keep: int | None = None) -> list[Path]:
    """Delete manifests past the newest ``keep`` of their type.

    ``keep`` of None reads :data:`KEEP_PER_TYPE` at the time of the call, so
    the constant stays the one place the number lives.

    Returns what was deleted. Files that are not manifests, ``latest-*``
    pointers, and anything :func:`pinned_paths` names are left alone, as is
    any file that will not delete -- pruning is housekeeping and never the
    reason a job reports a failure.
    """
    keep = max(1, KEEP_PER_TYPE if keep is None else keep)
    try:
        folder = manifests_dir(root)
        candidates = list(folder.glob("*.json"))
    except OSError:
        return []

    by_type: dict[str, list[Path]] = {}
    for path in candidates:
        if path.name.startswith("latest-"):
            continue
        type_name = path.name.split("-", 1)[0]
        if type_name not in TYPES:
            continue
        by_type.setdefault(type_name, []).append(path)

    stale = [
        path
        for paths in by_type.values()
        for path in sorted(paths, key=name_order, reverse=True)[keep:]
    ]
    if not stale:
        return []

    pinned = pinned_paths(root)
    deleted: list[Path] = []
    for path in stale:
        if path_key(path) in pinned:
            continue
        try:
            path.unlink()
        except OSError:
            continue
        deleted.append(path)
    return deleted
