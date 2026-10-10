from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable

from .app_paths import get_user_log_dir
from .branding import APP_NAME


_COPIED = re.compile(r"^copied (?P<name>.+) -> (?P<dir>.+)$")
_SKIP_IDENTICAL = re.compile(r"^(?P<name>.+?) identical file already backed up as (?P<other>.+)$")
_SKIP_EXISTS = re.compile(r"^(?P<name>.+) already exists$")
_DRY_RUN = re.compile(r"^\[DRY RUN\] (?P<name>.+) -> (?P<dir>.+)$")


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
            check = "not checked" if verify_mode == "none" else "verified"
            where = _relative_dir(match["dir"], destination)
            return f"{stamp}  OK  {match['name']} → {where} ({check})"
    elif level == "SKIP":
        match = _SKIP_IDENTICAL.match(message)
        if match:
            return f"{stamp}  SKIP  {match['name']} (identical, already backed up as {match['other']})"
        match = _SKIP_EXISTS.match(message)
        if match:
            return f"{stamp}  SKIP  {match['name']} (already exists)"
    elif level == "INFO":
        match = _DRY_RUN.match(message)
        if match:
            where = _relative_dir(match["dir"], destination)
            return f"{stamp}  PLAN  {match['name']} → {where}"
        return f"{stamp}  {message}"
    return f"{stamp}  {level}  {message}"


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
