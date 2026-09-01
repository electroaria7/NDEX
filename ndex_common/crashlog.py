"""Write uncaught exceptions to ``%LOCALAPPDATA%/NDEX/logs``."""

from __future__ import annotations

import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from ndex_common.version import NDEX_CHANNEL, NDEX_VERSION

APP_NAME = "NDEX"


def logs_dir() -> Path:
    candidates: list[Path] = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / APP_NAME / "logs")
    candidates.append(Path.home() / "AppData" / "Local" / APP_NAME / "logs")
    candidates.append(Path.home() / f".{APP_NAME.lower()}" / "logs")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    return candidates[-1]


def install_crash_logging(app_name: str = APP_NAME) -> None:
    """Install ``sys.excepthook`` (and thread hook) that records crash logs."""
    sys.excepthook = lambda exc_type, exc, tb: _handle_exception(app_name, exc_type, exc, tb)
    threading.excepthook = lambda args: _handle_exception(
        app_name, args.exc_type, args.exc_value, args.exc_traceback
    )


def write_crash_log(app_name: str, exc_type, exc, tb) -> Path | None:
    """Write one crash log. Returns the path, or None if the log could not be created."""
    try:
        directory = logs_dir()
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = directory / f"crash_{timestamp}.log"
        formatted = "".join(traceback.format_exception(exc_type, exc, tb))
        path.write_text(
            (
                f"NDEX {NDEX_VERSION} ({NDEX_CHANNEL})\n"
                f"App: {app_name}\n"
                f"Time: {datetime.now().isoformat(timespec='seconds')}\n\n"
                f"{formatted}"
            ),
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


def _handle_exception(app_name: str, exc_type, exc, tb) -> None:
    if exc_type is not None and issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    write_crash_log(app_name, exc_type, exc, tb)
    sys.__excepthook__(exc_type, exc, tb)
