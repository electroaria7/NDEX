"""Workspace state and background service adapters for the Frame UI."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, QRunnable, Qt, QThread, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage

from ndex_frame.core.geometry import build_render_plan, resolve_canvas
from ndex_frame.core.models import FramePreset, ImageOverride, MetadataPolicy, OutputProfile, SourceItem
from ndex_frame.imaging.color import prepare_master
from ndex_frame.services.cache import CacheError, PreviewCache
from ndex_frame.services.export_job import (
    CancelToken,
    ExportProgress,
    ExportRequest,
    ExportResult,
    plan_export,
    run_export,
)
from ndex_frame.services.importer import analyze_source, discover_files


class WorkspaceState:
    """Mutable in-memory session state; no Qt types or persistence."""

    def __init__(
        self,
        sources: list[SourceItem] | None = None,
        *,
        working_frame: FramePreset,
        output_profile: OutputProfile,
        output_directory: Path | None = None,
    ) -> None:
        self.sources = list(sources or [])
        self.selected_path = self.sources[0].path if self.sources else None
        self.working_frame = working_frame
        self.output_profile = output_profile
        self.output_directory = output_directory
        self.overrides: dict[Path, ImageOverride] = {}

    def replace_sources(self, sources: list[SourceItem]) -> None:
        self.sources = list(sources)
        self.selected_path = self.sources[0].path if self.sources else None
        self.overrides.clear()

    def select(self, path: Path) -> None:
        if path not in {source.path for source in self.sources}:
            raise ValueError(f"Unknown source: {path}")
        self.selected_path = path

    def source(self, path: Path) -> SourceItem:
        for source in self.sources:
            if source.path == path:
                return source
        raise ValueError(f"Unknown source: {path}")

    def effective_framing(self, path: Path) -> tuple[float, float, float]:
        override = self.overrides.get(path)
        if override is not None:
            return override.photo_scale, override.x, override.y
        frame = self.working_frame
        return frame.photo_scale, frame.x, frame.y

    def is_modified(self, path: Path) -> bool:
        return path in self.overrides

    def set_selected_framing(self, photo_scale: float, x: float, y: float) -> None:
        if self.selected_path is None:
            return
        self.overrides[self.selected_path] = ImageOverride(self.selected_path, photo_scale, x, y)

    def reset_override(self, path: Path) -> None:
        self.overrides.pop(path, None)

    def apply_current_framing_to_all(self) -> None:
        if self.selected_path is None:
            return
        photo_scale, x, y = self.effective_framing(self.selected_path)
        self.working_frame = replace(self.working_frame, photo_scale=photo_scale, x=x, y=y)
        self.overrides.clear()


class _ImportSignals(QObject):
    completed = Signal(object, object)
    failed = Signal(object, str)


class _ImportRunnable(QRunnable):
    def __init__(self, paths: list[Path], recursive: bool) -> None:
        super().__init__()
        self.paths = paths
        self.recursive = recursive
        self.signals = _ImportSignals()

    @Slot()
    def run(self) -> None:
        try:
            sources = [analyze_source(path) for path in discover_files(self.paths, self.recursive)]
            self.signals.completed.emit(self, sources)
        except Exception as error:
            self.signals.failed.emit(self, str(error) or error.__class__.__name__)


class _PreviewSignals(QObject):
    completed = Signal(object, object, object, str)
    failed = Signal(object, str)


class _PreviewRunnable(QRunnable):
    def __init__(self, source: SourceItem, cache: PreviewCache, max_edge: int) -> None:
        super().__init__()
        self.source = source
        self.cache = cache
        self.max_edge = max_edge
        self.signals = _PreviewSignals()

    @Slot()
    def run(self) -> None:
        try:
            try:
                cache_path = self.cache.get_or_create(self.source, self.max_edge)
                image = QImage(str(cache_path))
                if image.isNull():
                    raise CacheError(f"Could not read preview: {cache_path}")
                warning = ""
            except CacheError as cache_error:
                prepared = prepare_master(self.source.path, MetadataPolicy())
                try:
                    prepared.image.thumbnail((self.max_edge, self.max_edge), Image.Resampling.LANCZOS)
                    image = QImage(ImageQt(prepared.image)).copy()
                    warning = f"Preview cache unavailable; using direct preview. {cache_error}"
                finally:
                    prepared.image.close()
            self.signals.completed.emit(self, self.source.path, image, warning)
        except Exception as error:
            self.signals.failed.emit(self, str(error) or error.__class__.__name__)


class _ExportWorker(QObject):
    progress = Signal(object)
    completed = Signal(object)

    def __init__(self, snapshot: object, cancel: CancelToken) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.cancel = cancel

    @Slot()
    def run(self) -> None:
        result = run_export(self.snapshot, self.progress.emit, self.cancel)
        self.completed.emit(result)


class WorkspaceController(QObject):
    """Coordinates services while keeping all UI mutations on the GUI thread."""

    sourcesChanged = Signal()
    selectionChanged = Signal(object)
    previewReady = Signal(object, object, object, object)
    errorOccurred = Signal(str)
    exportProgress = Signal(object)
    exportFinished = Signal(object)
    busyChanged = Signal(bool)

    def __init__(
        self,
        state: WorkspaceState,
        *,
        preview_cache: PreviewCache | None = None,
        thread_pool: QThreadPool | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self.preview_cache = preview_cache or PreviewCache(Path.home() / ".ndex" / "frame" / "cache")
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        self._jobs: set[QRunnable] = set()
        self._export_thread: QThread | None = None
        self._export_worker: _ExportWorker | None = None
        self._cancel_token: CancelToken | None = None

    def import_paths(self, paths: list[Path], *, recursive: bool = False) -> None:
        job = _ImportRunnable(paths, recursive)
        self._jobs.add(job)
        job.signals.completed.connect(self._finish_import, Qt.ConnectionType.QueuedConnection)
        job.signals.failed.connect(self._fail_job, Qt.ConnectionType.QueuedConnection)
        self.busyChanged.emit(True)
        self.thread_pool.start(job)

    @Slot(object, object)
    def _finish_import(self, job: QRunnable, sources: list[SourceItem]) -> None:
        self._jobs.discard(job)
        self.state.replace_sources(sources)
        self.sourcesChanged.emit()
        self.busyChanged.emit(False)
        if self.state.selected_path is not None:
            self.selectionChanged.emit(self.state.selected_path)
            self.request_preview(self.state.selected_path)

    @Slot(object, str)
    def _fail_job(self, job: QRunnable, message: str) -> None:
        self._jobs.discard(job)
        self.busyChanged.emit(False)
        self.errorOccurred.emit(message)

    def select(self, path: Path) -> None:
        self.state.select(path)
        self.selectionChanged.emit(path)
        self.request_preview(path)

    def set_selected_framing(self, photo_scale: float, x: float, y: float) -> None:
        self.state.set_selected_framing(photo_scale, x, y)
        if self.state.selected_path is not None:
            self.selectionChanged.emit(self.state.selected_path)
            self.request_preview(self.state.selected_path)

    def reset_selected_override(self) -> None:
        if self.state.selected_path is not None:
            self.state.reset_override(self.state.selected_path)
            self.selectionChanged.emit(self.state.selected_path)
            self.request_preview(self.state.selected_path)

    def apply_current_framing_to_all(self) -> None:
        self.state.apply_current_framing_to_all()
        self.sourcesChanged.emit()
        if self.state.selected_path is not None:
            self.selectionChanged.emit(self.state.selected_path)
            self.request_preview(self.state.selected_path)

    def request_preview(self, path: Path, max_edge: int = 1600) -> None:
        source = self.state.source(path)
        job = _PreviewRunnable(source, self.preview_cache, max_edge)
        self._jobs.add(job)
        job.signals.completed.connect(self._finish_preview, Qt.ConnectionType.QueuedConnection)
        job.signals.failed.connect(self._fail_job, Qt.ConnectionType.QueuedConnection)
        self.thread_pool.start(job)

    @Slot(object, object, object, str)
    def _finish_preview(self, job: QRunnable, path: Path, image: QImage, warning: str) -> None:
        self._jobs.discard(job)
        if path != self.state.selected_path:
            return
        source = self.state.source(path)
        scale, x, y = self.state.effective_framing(path)
        canvas = resolve_canvas(self.state.output_profile.sizing, self.state.working_frame.ratio)
        # This is the exact export plan. PreviewWidget only projects this plan.
        plan = build_render_plan((source.oriented_width, source.oriented_height), canvas, scale, x, y)
        self.previewReady.emit(path, image, plan, self.state.working_frame.background)
        if warning:
            self.errorOccurred.emit(warning)

    def start_export(self, sources: list[SourceItem] | None = None, collision_policy: str = "rename") -> None:
        if self._export_thread is not None:
            raise RuntimeError("An export job is already running.")
        selected_sources = tuple(sources if sources is not None else self.state.sources)
        if not selected_sources or self.state.output_directory is None:
            raise ValueError("Sources and output directory are required.")
        request = ExportRequest(
            selected_sources,
            self.state.output_directory,
            self.state.working_frame,
            self.state.output_profile,
            tuple(self.state.overrides.values()),
            collision_policy,
        )
        snapshot = plan_export(request)
        cancel = CancelToken()
        thread = QThread(self)
        worker = _ExportWorker(snapshot, cancel)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._relay_export_progress, Qt.ConnectionType.QueuedConnection)
        worker.completed.connect(self._finish_export, Qt.ConnectionType.QueuedConnection)
        worker.completed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._export_thread, self._export_worker, self._cancel_token = thread, worker, cancel
        self.busyChanged.emit(True)
        thread.start()

    def cancel_export(self) -> None:
        if self._cancel_token is not None:
            self._cancel_token.cancel()

    @Slot(object)
    def _relay_export_progress(self, progress: ExportProgress) -> None:
        self.exportProgress.emit(progress)

    @Slot(object)
    def _finish_export(self, result: ExportResult) -> None:
        self._export_thread = None
        self._export_worker = None
        self._cancel_token = None
        self.busyChanged.emit(False)
        self.exportFinished.emit(result)
