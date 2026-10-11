"""Lazy, off-thread thumbnails for the Images list.

The window asks for the paths that are on screen (plus a margin). Work is done
by a small private thread pool, so previews and exports never wait behind it,
and a request that has scrolled out of range is dropped before it starts.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from ndex_frame.services.thumbnails import ThumbnailCache

THUMBNAIL_SIZE = 72  # logical pixels; DPI scaling is applied on top
MEMORY_LIMIT = 600


def _signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


class _Signals(QObject):
    done = Signal(object, object, object, bool)  # path, signature, QImage | None, failed


class _ThumbnailRunnable(QRunnable):
    def __init__(self, loader: "ThumbnailLoader", path: Path, signature, edge: int) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._loader = loader
        self.path = path
        self.signature = signature
        self.edge = edge

    @Slot()
    def run(self) -> None:
        loader = self._loader
        image: QImage | None = None
        failed = False
        # A request that scrolled out of range is skipped, not failed.
        if self.path in loader.wanted and not loader.stopped:
            try:
                made = QImage(str(loader.cache.get_or_create(self.path, self.edge)))
                image = None if made.isNull() else made
            except Exception:
                image = None
            failed = image is None
        loader.signals.done.emit(self.path, self.signature, image, failed)


class ThumbnailLoader(QObject):
    thumbnailReady = Signal(object)

    def __init__(
        self,
        cache: ThumbnailCache,
        *,
        size: int = THUMBNAIL_SIZE,
        device_pixel_ratio: float = 1.0,
        workers: int = 2,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.cache = cache
        self.size = size
        self.ratio = max(1.0, float(device_pixel_ratio))
        self.edge = round(size * self.ratio)
        self.wanted: set[Path] = set()
        self.stopped = False
        self._pending: set[Path] = set()
        self._failed: dict[Path, tuple[int, int] | None] = {}
        self._memory: OrderedDict[Path, tuple[tuple[int, int] | None, QPixmap]] = OrderedDict()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, workers))
        self.signals = _Signals(self)
        self.signals.done.connect(self._finished, Qt.ConnectionType.QueuedConnection)

    def pixmap_for(self, path: Path) -> QPixmap | None:
        """The thumbnail already in memory, without touching the disk."""
        entry = self._memory.get(path)
        return entry[1] if entry is not None else None

    def request(self, paths: Iterable[Path]) -> None:
        """Make exactly ``paths`` the wanted set, nearest first; load what is missing."""
        if self.stopped:
            return
        ordered = list(paths)
        self.wanted = set(ordered)
        for path in ordered:
            signature = _signature(path)
            entry = self._memory.get(path)
            if entry is not None and entry[0] == signature:
                self._memory.move_to_end(path)
                continue
            if path in self._pending or (path in self._failed and self._failed[path] == signature):
                continue
            self._pending.add(path)
            self._pool.start(_ThumbnailRunnable(self, path, signature, self.edge))

    @Slot(object, object, object, bool)
    def _finished(self, path: Path, signature, image: QImage | None, failed: bool) -> None:
        self._pending.discard(path)
        if self.stopped:
            return
        if image is None:
            # A real failure is remembered for this version of the file so it
            # is not retried on every scroll; a skipped request stays retryable.
            if failed:
                self._failed[path] = signature
            return
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(self.ratio)
        self._memory[path] = (signature, pixmap)
        self._memory.move_to_end(path)
        while len(self._memory) > MEMORY_LIMIT:
            self._memory.popitem(last=False)
        self.thumbnailReady.emit(path)

    def shutdown(self) -> None:
        """Drop queued work and wait for the (short) jobs already running."""
        self.stopped = True
        self.wanted = set()
        self._pool.clear()
        self._pool.waitForDone(3000)
