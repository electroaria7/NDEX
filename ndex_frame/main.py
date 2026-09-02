"""NDEX Frame command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ndex_common import settings
from ndex_common.branding import NDEX_FRAME_TITLE
from ndex_common.crashlog import install_crash_logging
from ndex_common.theme import apply_qt_theme
from ndex_frame.services.cache import PreviewCache
from ndex_frame.services.export_job import CancelToken, ExportRequest, ExportResult, plan_export, run_export
from ndex_frame.services.importer import analyze_source
from ndex_frame.services.presets import PresetStore
from ndex_frame.ui.main_window import MainWindow
from ndex_frame.ui.workspace import WorkspaceController, WorkspaceState

_BUILTIN_FRAME_ID = "builtin.white-3x4"
_BUILTIN_OUTPUT_ID = "builtin.instagram-feed-hq"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=NDEX_FRAME_TITLE)
    parser.add_argument("--open", action="store_true", help="Open the GUI (Launcher compatibility).")
    parser.add_argument("--source", type=Path, help="Master image folder to import after startup.")
    parser.add_argument(
        "--handoff",
        type=Path,
        help="Select-handoff manifest from Image Manager (JPG/PNG/TIFF list).",
    )
    parser.add_argument("--output", type=Path, help="Export output folder to preload.")
    parser.add_argument(
        "--smoke-export",
        nargs=2,
        type=Path,
        metavar=("SOURCE", "OUTPUT_DIR"),
        help=argparse.SUPPRESS,
    )
    return parser


def _data_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "NDEX" / "Frame"
    return settings.settings_path().parent.parent / "Frame"


def _attach_smoke_stdout() -> None:
    """Make stdout capturable from PowerShell for windowed packaged EXEs."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return

    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    std_output_handle = -11
    std_error_handle = -12
    attach_parent_process = 0xFFFFFFFF
    file_type_unknown = 0
    invalid_handle = ctypes.c_void_p(-1).value

    get_std_handle = kernel32.GetStdHandle
    get_std_handle.argtypes = [wintypes.DWORD]
    get_std_handle.restype = wintypes.HANDLE
    get_file_type = kernel32.GetFileType
    get_file_type.argtypes = [wintypes.HANDLE]
    get_file_type.restype = wintypes.DWORD

    def reopen(std_id: int, mode: str):
        handle = get_std_handle(std_id)
        if not handle or handle == invalid_handle:
            return None
        if (get_file_type(handle) & 0xFFFF) == file_type_unknown:
            return None
        try:
            descriptor = msvcrt.open_osfhandle(int(handle), os.O_TEXT)
            return os.fdopen(descriptor, mode, encoding="utf-8", errors="replace", buffering=1)
        except OSError:
            return None

    stdout = reopen(std_output_handle, "w")
    if stdout is None:
        kernel32.AttachConsole(attach_parent_process)
        stdout = reopen(std_output_handle, "w")
    if stdout is None:
        try:
            stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
        except OSError:
            stdout = None
    if stdout is not None:
        sys.stdout = stdout

    stderr = reopen(std_error_handle, "w")
    if stderr is not None:
        sys.stderr = stderr
    elif stdout is not None:
        sys.stderr = stdout


def _result_payload(result: ExportResult) -> dict[str, object]:
    return {
        "exported": result.exported,
        "skipped": result.skipped,
        "failed": result.failed,
        "cancelled": result.cancelled,
        "items": [
            {
                "source": str(item.source),
                "destination": str(item.destination),
                "state": item.state,
                "message": item.message,
            }
            for item in result.items
        ],
    }


def _run_smoke_export(source: Path, output_dir: Path) -> int:
    _attach_smoke_stdout()
    store = PresetStore(_data_root())
    frames = {preset.id: preset for preset in store.list_frames()}
    outputs = {preset.id: preset for preset in store.list_outputs()}
    snapshot = plan_export(
        ExportRequest(
            sources=(analyze_source(source),),
            output_dir=output_dir,
            frame=frames[_BUILTIN_FRAME_ID],
            output=outputs[_BUILTIN_OUTPUT_ID],
            overrides=(),
            collision_policy="rename",
        )
    )
    result = run_export(snapshot, lambda _event: None, CancelToken())
    print(json.dumps(_result_payload(result)), flush=True)
    return 0 if result.exported == 1 else 1


def _run_gui(args: argparse.Namespace) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_qt_theme()
    root = _data_root()
    store = PresetStore(root)
    state = WorkspaceState(
        working_frame=store.default_frame(),
        output_profile=store.default_output(),
    )
    controller = WorkspaceController(state, preview_cache=PreviewCache(root / "cache"))
    window = MainWindow(controller, preset_store=store)

    def remember_frame_session() -> None:
        folders: dict[str, str] = {}
        if controller.state.sources:
            folders["source"] = str(controller.state.sources[0].path.parent)
        if controller.state.output_directory is not None:
            folders["output"] = str(controller.state.output_directory)
        context = {"handoff": str(window.handoff_path) if window.handoff_path is not None else ""}
        if not folders and window.handoff_path is None:
            return
        from ndex_common.session import remember

        try:
            remember("frame", folders=folders, context=context)
        except OSError:
            pass

    def record_frame_export(result: ExportResult) -> None:
        from ndex_common.workflow import record_export

        source = ""
        if controller.state.sources:
            source = str(controller.state.sources[0].path.parent)
        destination = controller.state.output_directory or ""
        plan = window.pending_retry
        window.pending_retry = None
        record_export(
            source,
            destination,
            result,
            frame_preset=controller.state.working_frame.id,
            output_profile=controller.state.output_profile.id,
            context=plan.context() if plan is not None else None,
        )

    controller.sourcesChanged.connect(remember_frame_session)
    controller.exportFinished.connect(record_frame_export)
    if args.output is not None and args.output.is_dir():
        controller.state.output_directory = args.output
    window.show()
    window.sync_output_folder_label()
    handoff = args.handoff
    source = args.source
    if handoff is not None:
        QTimer.singleShot(0, lambda: window.queue_handoff(handoff))
    elif source is not None:
        QTimer.singleShot(0, lambda: window.queue_source(source))
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    install_crash_logging("NDEX Frame")
    args = build_parser().parse_args(argv)
    if args.smoke_export is not None:
        return _run_smoke_export(*args.smoke_export)
    return _run_gui(args)


if __name__ == "__main__":
    raise SystemExit(main())
