"""Background loading of grid thumbnails (decoding happens off the UI thread)."""
from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ThumbKey = tuple[str, int]


class ThumbnailLoader:
    """Decode and scale existing thumbnail files in worker threads.

    The UI thread tells the loader which tiles it wants right now (``want``);
    queued work for tiles that scrolled away is skipped when its turn comes, so
    a fast scroll never builds a backlog. Finished images are collected with
    ``drain`` and turned into Tk images by the caller.
    """

    def __init__(self, workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="im-thumb")
        self._done: queue.Queue[tuple[ThumbKey, Image.Image | None]] = queue.Queue()
        self._lock = threading.Lock()
        self._wanted: set[ThumbKey] = set()
        self._inflight: set[ThumbKey] = set()
        self._closed = False

    def want(self, keys) -> None:
        with self._lock:
            self._wanted = set(keys)

    def request(self, key: ThumbKey, fallback: Callable[[], Path | None] | None = None) -> bool:
        """Queue one tile unless it is already queued. Returns True if work was added."""
        with self._lock:
            if self._closed or key in self._inflight:
                return False
            self._inflight.add(key)
            self._wanted.add(key)
        self._pool.submit(self._load, key, fallback)
        return True

    def pending(self) -> int:
        with self._lock:
            return len(self._inflight)

    def drain(self, limit: int = 8) -> list[tuple[ThumbKey, Image.Image | None]]:
        out = []
        while len(out) < limit:
            try:
                out.append(self._done.get_nowait())
            except queue.Empty:
                break
        with self._lock:
            # A key stays "in flight" until the UI took its result, so it is never decoded twice.
            for key, _image in out:
                self._inflight.discard(key)
        return out

    def has_results(self) -> bool:
        return not self._done.empty()

    def close(self, wait: bool = True) -> None:
        """Stop taking work and drop the queue.

        By default this waits for the one decode per worker that may be running,
        so no thread is still writing a cache file once the window is gone.
        """
        with self._lock:
            self._closed = True
            self._wanted.clear()
        self._pool.shutdown(wait=wait, cancel_futures=True)

    def _load(self, key: ThumbKey, fallback) -> None:
        path, size = key
        with self._lock:
            skip = self._closed or key not in self._wanted
        if skip:
            with self._lock:
                self._inflight.discard(key)
            return
        result = _decode(Path(path), size)
        if result is None and fallback is not None:
            try:
                rebuilt = fallback()
            except Exception:
                rebuilt = None
            if rebuilt:
                result = _decode(Path(rebuilt), size)
        with self._lock:
            closed = self._closed
        if not closed:
            self._done.put((key, result))


def _decode(path: Path, size: int) -> Image.Image | None:
    try:
        with Image.open(path) as image:
            image.draft("RGB", (size * 2, size * 2))
            image.thumbnail((size, size), Image.Resampling.BILINEAR)
            return image.convert("RGB")
    except (OSError, ValueError, SyntaxError):
        return None
