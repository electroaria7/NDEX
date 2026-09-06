"""Verified file copies that never expose an incomplete destination."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile


def _digest(path: Path) -> bytes:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.digest()


def copy_verified(source: Path, destination: Path, *, overwrite: bool = False) -> None:
    """Stage beside the destination, verify contents, then publish atomically.

    A unique temporary name isolates concurrent copies. Non-overwrite commits
    fail if another writer has occupied the destination since planning.
    """
    source, destination = Path(source), Path(destination)
    if destination.exists() and source.samefile(destination):
        raise shutil.SameFileError(f"Source and destination are the same file: {source}")
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".ndex_tmp",
                                        dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        before = source.stat()
        shutil.copy2(source, temporary)
        if temporary.stat().st_size != before.st_size or _digest(source) != _digest(temporary):
            raise OSError(f"Copy verification failed: {source}")
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise OSError(f"Source changed during copy: {source}")
        if overwrite:
            os.replace(temporary, destination)
        elif os.name == "nt":
            os.rename(temporary, destination)  # Windows rename never replaces an existing file.
        else:
            os.link(temporary, destination)  # Atomic no-replace on POSIX.
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except PermissionError:
            # copy2 preserves the read-only attribute on Windows.
            temporary.chmod(stat.S_IWRITE | stat.S_IREAD)
            temporary.unlink(missing_ok=True)
