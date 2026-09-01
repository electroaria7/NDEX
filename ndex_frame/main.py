"""NDEX Frame command-line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ndex_common import settings
from ndex_common.branding import NDEX_FRAME_TITLE
from ndex_frame.services.cache import PreviewCache
from ndex_frame.services.presets import PresetStore
from ndex_frame.ui.main_window import MainWindow
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=NDEX_FRAME_TITLE)
    parser.add_argument("--open", action="store_true", help="Open the GUI (Launcher compatibility).")
    parser.add_argument("--source", type=Path, help="Master image folder to import after startup.")
    return parser


def _data_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "NDEX" / "Frame"
    return settings.settings_path().parent.parent / "Frame"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    root = _data_root()
    store = PresetStore(root)
    state = WorkspaceState(
        working_frame=store.default_frame(),
        output_profile=store.default_output(),
    )
    controller = WorkspaceController(state, preview_cache=PreviewCache(root / "cache"))
    window = MainWindow(controller, preset_store=store)
    window.show()
    if args.source is not None:
        QTimer.singleShot(0, lambda: window.queue_source(args.source))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
