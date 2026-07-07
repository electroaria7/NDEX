from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable

from .app_paths import get_user_log_dir
from .branding import APP_NAME


class AppLogger:
    def __init__(self, log_dir: Path | None = None, sink: Callable[[str], None] | None = None):
        self.log_dir = Path(log_dir) if log_dir else get_user_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.log_path = self.log_dir / f"ndex_{timestamp}.log"
        self.sink = sink
        self._lock = Lock()
        self.info(f"{APP_NAME} started")

    def _write(self, level: str, message: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{level}] {message}"
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        if self.sink:
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
