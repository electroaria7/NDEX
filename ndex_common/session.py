"""Per-app session documents for the NDEX workflow.

Sessions are JSON files under ``%LOCALAPPDATA%/NDEX/sessions/``. The latest
snapshot is also stored in ``settings.json`` under ``shared.sessions`` so the
launcher can read it with the rest of the shared settings. Legacy last-folder
keys stay valid; new fields are add-only.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ndex_common.jsonio import write_json_atomic
from ndex_common.settings import atomic_update, data_dir, load_all

KIND = "ndex.session"
SCHEMA_VERSION = 1
APPS = ("ndex_one", "image_manager", "auto_selector", "frame")

_LEGACY_FOLDERS = {
    "ndex_one": (("destination", ("last_destination",)), ("source", ("last_source",))),
    "image_manager": (("source", ("last_source",)),),
    "auto_selector": (
        ("selected_jpg", ("last_selected_jpg",)),
        ("raw_source", ("last_raw_source",)),
        ("work", ("last_work_folder",)),
    ),
    "frame": (("source", ("last_source",)), ("output", ("last_output",))),
}


def sessions_dir(root: Path | None = None) -> Path:
    path = (root or data_dir()) / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_path(app: str, root: Path | None = None) -> Path:
    if app not in APPS:
        raise ValueError(f"Unknown session app: {app}")
    return sessions_dir(root) / f"{app}.json"


def empty_session(app: str) -> dict[str, Any]:
    if app not in APPS:
        raise ValueError(f"Unknown session app: {app}")
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "app": app,
        "updated_at": "",
        "folders": {},
        "last_manifest": "",
        "context": {},
    }


def load_session(app: str, root: Path | None = None) -> dict[str, Any] | None:
    """Return the on-disk session document, or None if it is missing or invalid."""
    path = session_path(app, root)
    if not path.is_file():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _normalize(payload, app)


def session_from_settings(data: dict[str, Any], app: str) -> dict[str, Any]:
    """Build a session from ``shared.sessions`` or legacy last-folder keys."""
    shared = data.get("shared") if isinstance(data.get("shared"), dict) else {}
    stored = shared.get("sessions") if isinstance(shared.get("sessions"), dict) else {}
    snapshot = stored.get(app)
    if isinstance(snapshot, dict):
        normalized = _normalize(snapshot, app)
        if any(normalized["folders"].values()) or normalized["last_manifest"] or normalized["context"]:
            return normalized

    document = empty_session(app)
    section = data.get(app) if isinstance(data.get(app), dict) else {}
    folders: dict[str, str] = {}
    for folder_key, setting_keys in _LEGACY_FOLDERS[app]:
        value = ""
        for setting_key in setting_keys:
            if app == "ndex_one":
                raw = data.get(setting_key, "")
            else:
                raw = section.get(setting_key, "")
            if raw:
                value = str(raw)
                break
        if value:
            folders[folder_key] = value
    if app == "image_manager" and not folders.get("source"):
        backup_destination = str(data.get("last_destination") or "")
        if backup_destination:
            folders["source"] = backup_destination
    document["folders"] = folders
    return document


def remember(
    app: str,
    *,
    folders: dict[str, str] | None = None,
    last_manifest: str = "",
    context: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Write the session file and merge the snapshot into ``shared.sessions``."""
    current = load_session(app, root) or empty_session(app)
    merged_folders = dict(current.get("folders") or {})
    if folders:
        for key, value in folders.items():
            if value:
                merged_folders[key] = str(value)
    merged_context = dict(current.get("context") or {})
    if context:
        merged_context.update(context)
    document = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "app": app,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "folders": merged_folders,
        "last_manifest": last_manifest or str(current.get("last_manifest") or ""),
        "context": merged_context,
    }
    write_json_atomic(session_path(app, root), document)
    _store_snapshot(app, document)
    return document


def usable_handoff(document: dict[str, Any]) -> str:
    """Handoff path Frame can actually import, or "" when it cannot.

    A recorded handoff goes stale once the manifest is deleted or the files it
    lists are moved, so Continue checks the same conditions Frame does before
    it offers the handoff instead of a folder.
    """
    handoff = str((document.get("context") or {}).get("handoff") or "")
    if not handoff or not Path(handoff).is_file():
        return ""

    from ndex_common.manifest import handoff_files, load_manifest

    payload = load_manifest(Path(handoff))
    if payload is None or not handoff_files(payload):
        return ""
    return handoff


def usable(document: dict[str, Any]) -> bool:
    """True when Continue can reopen last work (folder or Frame handoff file)."""
    if document.get("app") == "frame" and usable_handoff(document):
        return True
    return any(Path(path).is_dir() for path in document.get("folders", {}).values() if path)


def preferred_folder(document: dict[str, Any]) -> str:
    """Folder shown in launcher status: first declared path, even if missing."""
    folders = document.get("folders") or {}
    for key, _setting_keys in _LEGACY_FOLDERS.get(str(document.get("app")), ()):
        value = str(folders.get(key) or "")
        if value:
            return value
    for value in folders.values():
        if value:
            return str(value)
    return ""


def launch_args(document: dict[str, Any]) -> list[str]:
    """Handoff argv for Continue. Missing folders are omitted (Empty fallback)."""
    if not usable(document):
        return ["--open"]
    app = str(document.get("app"))
    folders = document.get("folders") or {}
    args = ["--open"]
    if app == "ndex_one":
        _add_existing_dir(args, "--source", folders.get("source"))
        _add_existing_dir(args, "--destination", folders.get("destination"))
        return args
    if app == "image_manager":
        _add_existing_dir(args, "--source", folders.get("source"))
        return args
    if app == "auto_selector":
        _add_existing_dir(args, "--selected-jpg", folders.get("selected_jpg"))
        _add_existing_dir(args, "--raw-source", folders.get("raw_source"))
        _add_existing_dir(args, "--work-folder", folders.get("work"))
        return args
    if app == "frame":
        handoff = usable_handoff(document)
        if handoff:
            args.extend(["--handoff", handoff])
        else:
            _add_existing_dir(args, "--source", folders.get("source"))
        _add_existing_dir(args, "--output", folders.get("output"))
        return args
    return ["--open"]


def _add_existing_dir(args: list[str], flag: str, value: Any) -> None:
    text = str(value or "")
    if text and Path(text).is_dir():
        args.extend([flag, text])


def _store_snapshot(app: str, document: dict[str, Any]) -> None:
    def mutator(data: dict) -> dict:
        shared = data.get("shared")
        shared = dict(shared) if isinstance(shared, dict) else {}
        sessions = shared.get("sessions")
        sessions = dict(sessions) if isinstance(sessions, dict) else {}
        sessions[app] = deepcopy(document)
        shared["sessions"] = sessions
        data["shared"] = shared
        return data

    try:
        atomic_update(mutator)
    except OSError:
        pass


def _normalize(payload: dict[str, Any], app: str) -> dict[str, Any]:
    document = empty_session(app)
    if payload.get("kind") not in (KIND, None, ""):
        return document
    folders = payload.get("folders")
    document["folders"] = dict(folders) if isinstance(folders, dict) else {}
    document["last_manifest"] = str(payload.get("last_manifest") or "")
    context = payload.get("context")
    document["context"] = dict(context) if isinstance(context, dict) else {}
    document["updated_at"] = str(payload.get("updated_at") or "")
    document["schema_version"] = SCHEMA_VERSION
    return document


def latest_from_settings(data: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Return session documents for every app, hydrating from settings when needed."""
    payload = data if data is not None else load_all()
    return {app: session_from_settings(payload, app) for app in APPS}
