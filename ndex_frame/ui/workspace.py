"""Workspace state and background service adapters for the Frame UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, QRunnable, Qt, QThread, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from ndex_common import settings

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
    completed = Signal(object, object, str)
    failed = Signal(object, str)


class _ImportRunnable(QRunnable):
    def __init__(self, paths: list[Path], recursive: bool) -> None:
        super().__init__()
        self.paths = paths
        self.recursive = recursive
        self.cancel = CancelToken()
        self.signals = _ImportSignals()
        self.source_folder = next((path.resolve() for path in paths if path.is_dir()), None)

    @Slot()
    def run(self) -> None:
        # One unreadable file must not take the rest of the batch with it:
        # the good ones open, the bad ones are named.
        sources = []
        problems = []
        try:
            files = discover_files(self.paths, self.recursive)
        except Exception as error:
            self.signals.failed.emit(self, str(error) or error.__class__.__name__)
            return
        for path in files:
            if self.cancel.is_cancelled():
                self.signals.completed.emit(self, [], "")
                return
            try:
                sources.append(analyze_source(path))
            except Exception as error:
                problems.append(f"{path.name}: {str(error) or error.__class__.__name__}")
        if not sources:
            self.signals.failed.emit(self, "; ".join(problems) or "No images could be opened.")
            return
        warning = ""
        if problems:
            warning = f"Could not open {len(problems)} file(s): " + "; ".join(problems[:3])
        self.signals.completed.emit(self, sources, warning)


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
    failed = Signal(str)

    def __init__(self, snapshot: object, cancel: CancelToken) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.cancel = cancel

    @Slot()
    def run(self) -> None:
        try:
            result = run_export(self.snapshot, self.progress.emit, self.cancel)
        except Exception as error:
            self.failed.emit(str(error) or error.__class__.__name__)
        else:
            self.completed.emit(result)


class WorkspaceController(QObject):
    """Coordinates services while keeping all UI mutations on the GUI thread."""

    sourcesChanged = Signal()
    selectionChanged = Signal(object)
    previewReady = Signal(object, object, object, object)
    errorOccurred = Signal(str)
    # Job-shaped outcomes a window can act on, next to the human-readable
    # errorOccurred that still fires for the status bar.
    importFailed = Signal(str)
    exportAborted = Signal(str)
    exportProgress = Signal(object)
    exportFinished = Signal(object)
    busyChanged = Signal(bool)
    shutdownFinished = Signal()

    def __init__(
        self,
        state: WorkspaceState,
        *,
        preview_cache: PreviewCache | None = None,
        thread_pool: QThreadPool | None = None,
        settings_writer: Callable[[str, dict], None] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self.preview_cache = preview_cache or PreviewCache(Path.home() / ".ndex" / "frame" / "cache")
        self.thread_pool = thread_pool or QThreadPool(self)
        self._settings_writer = settings_writer or settings.update_section
        self._jobs: set[QRunnable] = set()
        self._export_thread: QThread | None = None
        self._export_worker: _ExportWorker | None = None
        self._cancel_token: CancelToken | None = None
        self._pending_export_result: ExportResult | None = None
        self._current_import: _ImportRunnable | None = None
        self._preview_jobs: dict[tuple, _PreviewRunnable] = {}
        self._requested_preview_key: tuple | None = None
        self._preview_image: tuple[tuple, QImage] | None = None
        self._shutting_down = False
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(20)
        self._shutdown_timer.timeout.connect(self._poll_shutdown)
        self._export_error = ""

    def import_paths(self, paths: list[Path], *, recursive: bool = False) -> None:
        if self._shutting_down:
            return
        if self._current_import is not None:
            self._current_import.cancel.cancel()
        job = _ImportRunnable(paths, recursive)
        self._current_import = job
        self._jobs.add(job)
        job.signals.completed.connect(self._finish_import, Qt.ConnectionType.QueuedConnection)
        job.signals.failed.connect(self._fail_job, Qt.ConnectionType.QueuedConnection)
        self.busyChanged.emit(True)
        self.thread_pool.start(job)

    @Slot(object, object, str)
    def _finish_import(self, job: QRunnable, sources: list[SourceItem], warning: str = "") -> None:
        self._jobs.discard(job)
        if job is not self._current_import or self._shutting_down:
            return
        self._current_import = None
        self._requested_preview_key = None
        if warning:
            self.errorOccurred.emit(warning)
        self.state.replace_sources(sources)
        source_folder = getattr(job, "source_folder", None)
        if source_folder is not None:
            try:
                self._settings_writer("frame", {"last_source": str(source_folder)})
            except OSError:
                pass
        self.sourcesChanged.emit()
        self._emit_busy()
        if self.state.selected_path is not None:
            self.selectionChanged.emit(self.state.selected_path)
            self.request_preview(self.state.selected_path)

    @Slot(object, str)
    def _fail_job(self, job: QRunnable, message: str) -> None:
        self._jobs.discard(job)
        self._forget_preview_job(job)
        if self._shutting_down:
            return
        if isinstance(job, _ImportRunnable):
            if job is not self._current_import:
                return
            self._current_import = None
            self._emit_busy()
            self.importFailed.emit(message)
        self.errorOccurred.emit(message)

    def _emit_busy(self) -> None:
        self.busyChanged.emit(self._current_import is not None or self._export_thread is not None)

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

    def update_working_frame(self, **changes: object) -> None:
        self.state.working_frame = replace(self.state.working_frame, **changes)
        if self.state.selected_path is not None:
            self.request_preview(self.state.selected_path)

    def request_preview(self, path: Path, max_edge: int = 1600) -> None:
        if self._shutting_down:
            return
        source = self.state.source(path)
        key = self._preview_key(path, max_edge)
        self._requested_preview_key = key
        if self._preview_image is not None and self._preview_image[0] == key:
            self._emit_preview(path, self._preview_image[1])
            return
        if key in self._preview_jobs:
            return
        job = _PreviewRunnable(source, self.preview_cache, max_edge)
        job.preview_key = key
        self._preview_jobs[key] = job
        self._jobs.add(job)
        job.signals.completed.connect(self._finish_preview, Qt.ConnectionType.QueuedConnection)
        job.signals.failed.connect(self._fail_job, Qt.ConnectionType.QueuedConnection)
        self.thread_pool.start(job)

    @Slot(object, object, object, str)
    def _finish_preview(self, job: QRunnable, path: Path, image: QImage, warning: str) -> None:
        self._jobs.discard(job)
        self._forget_preview_job(job)
        if self._shutting_down or path != self.state.selected_path:
            return
        key = getattr(job, "preview_key", None)
        if key is not None:
            if key != self._requested_preview_key or key != self._preview_key(path, job.max_edge):
                return
            self._preview_image = (key, image)
        self._emit_preview(path, image)
        if warning:
            self.errorOccurred.emit(warning)

    @staticmethod
    def _preview_key(path: Path, max_edge: int) -> tuple:
        try:
            stat = path.stat()
            return path, max_edge, stat.st_size, stat.st_mtime_ns
        except OSError:
            return path, max_edge, None, None

    def _forget_preview_job(self, job: QRunnable) -> None:
        key = getattr(job, "preview_key", None)
        if self._preview_jobs.get(key) is job:
            self._preview_jobs.pop(key, None)

    def _emit_preview(self, path: Path, image: QImage) -> None:
        source = self.state.source(path)
        scale, x, y = self.state.effective_framing(path)
        canvas = resolve_canvas(self.state.output_profile.sizing, self.state.working_frame.ratio)
        # This is the exact export plan. PreviewWidget only projects this plan.
        plan = build_render_plan((source.oriented_width, source.oriented_height), canvas, scale, x, y)
        self.previewReady.emit(path, image, plan, self.state.working_frame.background)

    def start_export(self, sources: list[SourceItem] | None = None, collision_policy: str = "rename") -> None:
        if self._shutting_down:
            raise RuntimeError("The workspace is closing.")
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
        worker.completed.connect(self._record_export_result, Qt.ConnectionType.QueuedConnection)
        worker.completed.connect(worker.deleteLater)
        worker.completed.connect(thread.quit)
        worker.failed.connect(self._record_export_error, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(worker.deleteLater)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._export_thread_finished, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(thread.deleteLater)
        self._pending_export_result = None
        self._export_error = ""
        self._export_thread, self._export_worker, self._cancel_token = thread, worker, cancel
        self.busyChanged.emit(True)
        thread.start()

    def cancel_export(self) -> None:
        if self._cancel_token is not None:
            self._cancel_token.cancel()

    def shutdown(self) -> bool:
        """Begin cooperative shutdown; keep the event loop available for results."""
        self._shutting_down = True
        self.cancel_export()
        for job in self._jobs:
            if isinstance(job, _ImportRunnable):
                job.cancel.cancel()
        if self._shutdown_complete():
            return True
        self._shutdown_timer.start()
        return False

    def _shutdown_complete(self) -> bool:
        return self._export_thread is None and not self._jobs and self.thread_pool.activeThreadCount() == 0

    @Slot()
    def _poll_shutdown(self) -> None:
        if self._shutdown_complete():
            self._shutdown_timer.stop()
            self.shutdownFinished.emit()

    @Slot(object)
    def _relay_export_progress(self, progress: ExportProgress) -> None:
        self.exportProgress.emit(progress)

    @Slot(object)
    def _record_export_result(self, result: ExportResult) -> None:
        self._pending_export_result = result

    @Slot(str)
    def _record_export_error(self, message: str) -> None:
        self._export_error = message

    @Slot()
    def _export_thread_finished(self) -> None:
        result = self._pending_export_result
        self._export_thread = None
        self._export_worker = None
        self._cancel_token = None
        self._pending_export_result = None
        self._emit_busy()
        if result is not None:
            self.exportFinished.emit(result)
        else:
            message = self._export_error or "Export worker stopped without a result."
            self.exportAborted.emit(message)
            self.errorOccurred.emit(message)
