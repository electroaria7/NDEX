from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime
import os
from pathlib import Path
from threading import Event
import time
from typing import Callable

from ..core.file_types import is_supported_image, media_type_for_path
from ..core.models import ImageMetadata, ImageRecord, PairStatus, ScanResult
from .cache import CacheManager
from .catalog import Catalog
from .metadata import MetadataReader

ProgressCallback = Callable[[int, int, Path], None]
# Receives the saved records (with ids and current marks) of each flushed batch.
BatchCallback = Callable[[list[ImageRecord]], None]

FIRST_CHUNK = 20
CHUNK = 100
BATCH_RECORDS = 100
BATCH_SECONDS = 0.2


class ScanCancelled(Exception):
    """A scan stopped early. Records catalogued before the stop are kept.

    ``listed`` of ``total`` files were saved; ``catalog_path`` is None when the
    scan stopped before the catalog was touched.
    """

    def __init__(self, listed: int = 0, total: int = 0, catalog_path: Path | None = None):
        super().__init__("Scan cancelled")
        self.listed = listed
        self.total = total
        self.catalog_path = catalog_path


def _check_cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ScanCancelled()


class ImageScanner:
    def __init__(self, metadata_reader: MetadataReader | None = None):
        self.metadata_reader = metadata_reader or MetadataReader()

    def scan(
        self,
        source_dir: Path,
        recursive: bool = True,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
        batch_callback: BatchCallback | None = None,
    ) -> ScanResult:
        source_dir = Path(source_dir).resolve()
        cache_dir = source_dir / ".dsb_cache"
        _check_cancelled(cancel_event)
        cache = CacheManager(cache_dir, self.metadata_reader)

        paths = self._find_images(source_dir, recursive, cancel_event)
        pair_status = self._pair_status_by_path(paths)
        catalog_path = cache_dir / "catalog.sqlite"
        catalog = Catalog(catalog_path)
        saved: list[ImageRecord] = []
        try:
            try:
                self._catalog_paths(
                    paths, pair_status, cache, catalog, saved,
                    progress_callback, cancel_event, batch_callback,
                )
            except ScanCancelled as exc:
                # Everything flushed so far stays in the catalog; nothing is removed.
                exc.listed, exc.total, exc.catalog_path = len(saved), len(paths), catalog_path
                raise
            _check_cancelled(cancel_event)
            catalog.remove_missing_under(source_dir, {record.file_path for record in saved}, recursive=recursive)
            catalog.set_setting("last_opened_folder", str(source_dir))
        finally:
            catalog.close()
        return ScanResult(source_dir=source_dir, catalog_path=catalog_path, records=saved)

    def _catalog_paths(
        self,
        paths: list[Path],
        pair_status: dict[Path, PairStatus],
        cache: CacheManager,
        catalog: Catalog,
        saved: list[ImageRecord],
        progress_callback: ProgressCallback | None,
        cancel_event: Event | None,
        batch_callback: BatchCallback | None,
    ) -> None:
        total = len(paths)
        known = catalog.records_by_path()
        pending: list[ImageRecord] = []
        last_flush = time.monotonic()

        def flush() -> None:
            nonlocal last_flush
            last_flush = time.monotonic()
            if not pending:
                return
            batch = catalog.upsert_images(pending)
            pending.clear()
            saved.extend(batch)
            if batch_callback:
                batch_callback(batch)

        done = 0
        start = 0
        chunk_size = FIRST_CHUNK
        try:
            while start < total:
                _check_cancelled(cancel_event)
                end = min(total, start + chunk_size)
                # Keep a RAW+JPG pair inside one chunk so a shot never straddles two batches.
                while end < total and _pair_group_id(paths[end]) == _pair_group_id(paths[end - 1]):
                    end += 1
                chunk = paths[start:end]
                chunk_size = CHUNK

                stats = {path: path.stat() for path in chunk}
                reusable = {
                    path: known[str(path)]
                    for path in chunk
                    if str(path) in known and self._reusable(known[str(path)], stats[path])
                }
                to_read = [path for path in chunk if path not in reusable]
                if progress_callback:
                    progress_callback(done, total, chunk[0])
                metadata_by_path = self.metadata_reader.read_batch(to_read) if to_read else {}
                _check_cancelled(cancel_event)

                for offset, path in enumerate(chunk):
                    _check_cancelled(cancel_event)
                    done += 1
                    if progress_callback:
                        progress_callback(done, total, path)
                    existing = reusable.get(path)
                    if existing is not None:
                        # Same file as last time: keep metadata, thumbnail and marks; only
                        # the pairing can change when its RAW/JPG partner appeared or left.
                        record = replace(
                            existing,
                            pair_group_id=_pair_group_id(path),
                            pair_status=pair_status.get(path, "unknown"),
                        )
                    else:
                        record = self._build_record(
                            path, metadata_by_path.get(path), cache, pair_status.get(path, "unknown"), stats[path],
                        )
                    pending.append(record)
                    last_of_shot = offset + 1 == len(chunk) or _pair_group_id(chunk[offset + 1]) != _pair_group_id(path)
                    if last_of_shot and (
                        len(pending) >= BATCH_RECORDS or time.monotonic() - last_flush >= BATCH_SECONDS
                    ):
                        flush()
                start = end
        except ScanCancelled:
            flush()  # keep what was catalogued before the stop
            raise
        flush()

    def _reusable(self, existing: ImageRecord, stat: os.stat_result) -> bool:
        """True when nothing about the file or its cached assets needs rebuilding."""
        if existing.size_bytes != stat.st_size or existing.mtime_ns != stat.st_mtime_ns:
            return False
        if existing.proxy_status in ("failed", "pending"):
            return False  # retry: the preview extractor may work now
        if not existing.has_exif and getattr(self.metadata_reader, "exiftool_path", None):
            return False  # metadata was read without ExifTool earlier
        if existing.thumbnail_path is None or not existing.thumbnail_path.exists():
            return False
        return existing.display_source is None or existing.display_source.exists()

    @staticmethod
    def _build_record(
        path: Path,
        metadata: ImageMetadata | None,
        cache: CacheManager,
        pair_status: PairStatus,
        stat: os.stat_result,
    ) -> ImageRecord:
        display_source, thumbnail_path, proxy_status = cache.ensure_display_assets(path)
        return ImageRecord(
            id=None,
            file_path=path,
            file_ext=path.suffix.lower().lstrip("."),
            base_name=path.stem,
            media_type=media_type_for_path(path),
            pair_group_id=_pair_group_id(path),
            pair_status=pair_status,
            display_source=display_source,
            proxy_path=display_source if path.suffix.lower() not in {".jpg", ".jpeg"} else None,
            thumbnail_path=thumbnail_path,
            capture_datetime=metadata.capture_datetime if metadata else None,
            file_modified_datetime=datetime.fromtimestamp(stat.st_mtime),
            camera_model=metadata.camera_model if metadata else "",
            lens_model=metadata.lens_model if metadata else "",
            focal_length=metadata.focal_length if metadata else "",
            exposure_time=metadata.exposure_time if metadata else "",
            aperture=metadata.aperture if metadata else "",
            iso=metadata.iso if metadata else "",
            exposure_compensation=metadata.exposure_compensation if metadata else "",
            white_balance=metadata.white_balance if metadata else "",
            color_space=metadata.color_space if metadata else "",
            width=metadata.width if metadata else None,
            height=metadata.height if metadata else None,
            file_size=metadata.file_size if metadata else "",
            gps=metadata.gps if metadata else "",
            has_exif=metadata.has_exif if metadata else False,
            has_proxy=display_source is not None and media_type_for_path(path) == "raw",
            proxy_status=proxy_status,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )

    @staticmethod
    def _find_images(source_dir: Path, recursive: bool, cancel_event: Event | None = None) -> list[Path]:
        paths = []
        def walk_error(error: OSError) -> None:
            # An incomplete traversal must never remove unseen catalog rows.
            raise error

        for directory, subdirs, names in os.walk(source_dir, onerror=walk_error):
            _check_cancelled(cancel_event)
            subdirs[:] = [name for name in subdirs if name.casefold() != ".dsb_cache"] if recursive else []
            for name in names:
                _check_cancelled(cancel_event)
                path = Path(directory) / name
                if is_supported_image(path) and path.is_file():
                    paths.append(path.resolve())
        # Files of one shot (same folder and stem) stay adjacent so batches never split a pair.
        return sorted(paths, key=lambda path: (str(path.parent).lower(), path.stem.lower(), path.suffix.lower()))

    @staticmethod
    def _pair_status_by_path(paths: list[Path]) -> dict[Path, PairStatus]:
        groups: dict[str, list[Path]] = defaultdict(list)
        for path in paths:
            groups[_pair_group_id(path)].append(path)

        statuses: dict[Path, PairStatus] = {}
        for group_paths in groups.values():
            has_jpg = any(media_type_for_path(path) == "jpg" for path in group_paths)
            has_raw = any(media_type_for_path(path) == "raw" for path in group_paths)
            if has_jpg and has_raw:
                status: PairStatus = "raw_jpg_pair"
            elif has_raw:
                status = "raw_only"
            elif has_jpg:
                status = "jpg_only"
            else:
                status = "unknown"
            for path in group_paths:
                statuses[path] = status
        return statuses


def _pair_group_id(path: Path) -> str:
    # RAW/JPG pairs only count within one folder: camera counters roll over across cards.
    return f"{str(path.parent).casefold()}|{path.stem.casefold()}"
