"""Reentrant thread/process locks for short on-disk state transactions.

Lock order: workflow.lock first, then settings.json.lock. Never acquire a
workflow lock from inside a settings mutator. Lock files stay on disk: deleting
one while another process has it open would split the lock into two identities.
"""

from __future__ import annotations

import os
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_THREAD_LOCK = threading.RLock()
_HELD: set[str] = set()  # Accessed only while _THREAD_LOCK is held.


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Lock a persistent file; nested acquisition by the owner is harmless."""
    key = os.path.normcase(str(path.resolve()))
    with _THREAD_LOCK:
        if key in _HELD:
            yield
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                # Reading this byte before acquiring it fails when another
                # Windows process owns the mandatory byte-range lock.
                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b"\0")
                    handle.flush()
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            _HELD.add(key)
            try:
                yield
            finally:
                _HELD.remove(key)
                if sys.platform == "win32":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
