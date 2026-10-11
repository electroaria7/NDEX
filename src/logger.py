from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable

from ndex_common.i18n import _

from .app_paths import get_user_log_dir
from .branding import APP_NAME


_COPIED = re.compile(r"^copied (?P<name>.+) -> (?P<dir>.+)$")
_SKIP_IDENTICAL = re.compile(r"^(?P<name>.+?) identical file already backed up as (?P<other>.+)$")
_SKIP_EXISTS = re.compile(r"^(?P<name>.+) already exists$")
_DRY_RUN = re.compile(r"^\[DRY RUN\] (?P<name>.+) -> (?P<dir>.+)$")
_SOURCE = re.compile(r"^Source: (?P<path>.+)$")
_DESTINATION = re.compile(r"^Destination: (?P<path>.+)$")
_FOUND = re.compile(r"^Found (?P<count>\d+) supported files$")
_STARTED = re.compile(r"^(?P<app>.+) started$")
_VERIFY_FAILED = re.compile(
    r"^(?P<name>.+) verification failed after copy \((?P<mode>.+)\); existing backup left untouched$"
)
_FAILED = re.compile(r"^(?P<name>.+) failed: (?P<error>.+)$")
_TEMP_FILE = re.compile(r"^could not remove temp file (?P<name>.+)$")
_UNREADABLE = re.compile(r"^Skipping (?P<name>.+): file is no longer readable \((?P<error>.+)\)\.$")
_METADATA_FALLBACK = re.compile(
    r"^Metadata read failed for (?P<name>.+)\. Using file modified time as fallback\.$"
)
_EXIF_FILE = re.compile(r"^ExifTool metadata read failed for (?P<name>.+): (?P<error>.+)$")
_EXIF_BATCH = re.compile(
    r"^ExifTool batch read failed for (?P<count>\d+) files: (?P<error>.+)\. Retrying with smaller batches\.$"
)


def _translate_message(message: str) -> str:
    """The on-screen wording of a log message. The log file keeps English."""
    fixed = {
        "Backup completed": _("Backup completed"),
        "Dry run completed": _("Dry run completed"),
        "Backup cancelled by user": _("Backup cancelled by user"),
        "ExifTool was not found. RAW metadata will use fallback dates when needed.": _(
            "ExifTool was not found. RAW metadata will use fallback dates when needed."
        ),
    }
    if message in fixed:
        return fixed[message]
    match = _FOUND.match(message)
    if match:
        return _("Found {count} supported files").format(count=match["count"])
    match = _SOURCE.match(message)
    if match:
        return _("Source: {path}").format(path=match["path"])
    match = _DESTINATION.match(message)
    if match:
        return _("Destination: {path}").format(path=match["path"])
    match = _STARTED.match(message)
    if match:
        return _("{app} started").format(app=match["app"])
    match = _VERIFY_FAILED.match(message)
    if match:
        return _(
            "{name} verification failed after copy ({mode}); existing backup left untouched"
        ).format(name=match["name"], mode=match["mode"])
    match = _TEMP_FILE.match(message)
    if match:
        return _("could not remove temp file {name}").format(name=match["name"])
    match = _UNREADABLE.match(message)
    if match:
        return _("Skipping {name}: file is no longer readable ({error}).").format(
            name=match["name"], error=match["error"]
        )
    match = _METADATA_FALLBACK.match(message)
    if match:
        return _("Metadata read failed for {name}. Using file modified time as fallback.").format(
            name=match["name"]
        )
    match = _EXIF_FILE.match(message)
    if match:
        return _("ExifTool metadata read failed for {name}: {error}").format(
            name=match["name"], error=match["error"]
        )
    match = _EXIF_BATCH.match(message)
    if match:
        return _("ExifTool batch read failed for {count} files: {error}. Retrying with smaller batches.").format(
            count=match["count"], error=match["error"]
        )
    match = _FAILED.match(message)
    if match:
        return _("{name} failed: {error}").format(name=match["name"], error=match["error"])
    return message


def _level_label(level: str) -> str:
    return {
        "OK": _("OK"), "SKIP": _("SKIP"), "PLAN": _("PLAN"), "WARN": _("WARN"), "ERROR": _("ERROR"),
    }.get(level, level)


def _relative_dir(folder: str, destination: str | None) -> str:
    """The date/type part of a destination folder, with forward slashes."""
    folder = folder.replace("\\", "/")
    if destination:
        root = destination.replace("\\", "/").rstrip("/") + "/"
        if folder.lower().startswith(root.lower()):
            return folder[len(root):]
    return folder


def format_display_line(
    level: str,
    message: str,
    *,
    destination: str | None = None,
    verify_mode: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """One readable line for the on-screen log, or None to leave it out.

    The log file keeps its full, detailed lines; the window shows one line
    per file ("OK IMG_1024.JPG -> 2026/09/0907/jpg (verified)").
    """
    stamp = f"{now or datetime.now():%H:%M:%S}"
    if level == "OK":
        if message.startswith("verified "):
            return None  # folded into the "copied" line
        match = _COPIED.match(message)
        if match:
            check = _("not checked") if verify_mode == "none" else _("verified")
            where = _relative_dir(match["dir"], destination)
            return f"{stamp}  {_level_label('OK')}  {match['name']} → {where} ({check})"
    elif level == "SKIP":
        match = _SKIP_IDENTICAL.match(message)
        if match:
            note = _("identical, already backed up as {other}").format(other=match["other"])
            return f"{stamp}  {_level_label('SKIP')}  {match['name']} ({note})"
        match = _SKIP_EXISTS.match(message)
        if match:
            return f"{stamp}  {_level_label('SKIP')}  {match['name']} ({_('already exists')})"
    elif level == "INFO":
        match = _DRY_RUN.match(message)
        if match:
            where = _relative_dir(match["dir"], destination)
            return f"{stamp}  {_level_label('PLAN')}  {match['name']} → {where}"
        return f"{stamp}  {_translate_message(message)}"
    return f"{stamp}  {_level_label(level)}  {_translate_message(message)}"


class AppLogger:
    def __init__(
        self,
        log_dir: Path | None = None,
        sink: Callable[[str], None] | None = None,
        display: Callable[[str, str], str | None] | None = None,
    ):
        self.log_dir = Path(log_dir) if log_dir else get_user_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.log_path = self.log_dir / f"ndex_{timestamp}.log"
        self.sink = sink
        # Turns (level, message) into the line the sink shows; the file keeps the full line.
        self.display = display
        self._lock = Lock()
        self.info(f"{APP_NAME} started")

    def _write(self, level: str, message: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{level}] {message}"
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        if self.sink:
            if self.display is not None:
                line = self.display(level, message)
                if line is None:
                    return
            self.sink(line)

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def ok(self, message: str) -> None:
        self._write("OK", message)

    def skip(self, message: str) -> None:
        self._write("SKIP", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)
