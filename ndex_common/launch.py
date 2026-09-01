"""Launch sibling NDEX apps (Adobe-style handoff between programs).

Resolution order:
1. Packaged layout: the current EXE's folder, then ``Apps\\`` beside it.
   Frozen apps do not search parent directories.
2. Known dist folders in the repo tree.
3. Dev fallback: run the app module with the current Python interpreter.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP_COMMANDS = {
    "ndex_one": ("NDEX_One.exe", "main"),
    "image_manager": ("NDEX_Image_Manager.exe", "dsb_image_manager.main"),
    "auto_selector": ("NDEX_Auto_Selector.exe", "ndex_auto_selector.main"),
    "frame": ("NDEX_Frame.exe", "ndex_frame.main"),
    "launcher": ("NDEX_Launcher.exe", "ndex_launcher.main"),
}

_EXE_ALIASES = {
    "NDEX_One.exe": ("NDEX_One_OneFile.exe",),
}

_DIST_SUBDIRS = (
    "dist",
    "dsb_image_manager/dist",
    "ndex_auto_selector/dist",
    "ndex_frame/dist",
    "ndex_launcher/dist",
)


def launch_app(app_key: str, extra_args: list[str] | tuple[str, ...] = ()) -> bool:
    """Start another NDEX app detached. Returns True when a launch was attempted."""
    exe_name, module_name = APP_COMMANDS[app_key]

    executable = _find_executable(exe_name)
    if executable is not None:
        subprocess.Popen([str(executable), *extra_args], close_fds=True)
        return True

    if getattr(sys, "frozen", False):
        return False

    repo_root = _repo_root()
    if repo_root is not None:
        subprocess.Popen(
            [sys.executable, "-m", module_name, *extra_args],
            cwd=str(repo_root),
            close_fds=True,
        )
        return True
    return False


def _candidate_names(exe_name: str) -> tuple[str, ...]:
    return (exe_name, *_EXE_ALIASES.get(exe_name, ()))


def _find_executable(exe_name: str) -> Path | None:
    names = _candidate_names(exe_name)
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        # Packaged layout only: this EXE's folder, then Apps\ beside it.
        # Do not walk parent directories or the PyInstaller extract tree.
        exe_dir = Path(sys.executable).resolve().parent
        for name in names:
            candidates.append(exe_dir / name)
            candidates.append(exe_dir / "Apps" / name)
    else:
        repo_root = _repo_root()
        if repo_root is not None:
            for subdir in _DIST_SUBDIRS:
                for name in names:
                    candidates.append(repo_root / subdir / name)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _repo_root() -> Path | None:
    root = Path(__file__).resolve().parent.parent
    if (root / "ndex_common").is_dir():
        return root
    return None
