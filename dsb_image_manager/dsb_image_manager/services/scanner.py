from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import os
from pathlib import Path
from threading import Event
from typing import Callable

from ..core.file_types import is_supported_image, media_type_for_path
from ..core.models import ImageRecord, PairStatus, ScanResult
from .cache import CacheManager
from .catalog import Catalog
from .metadata import MetadataReader

ProgressCallback = Callable[[int, int, Path], None]


class ScanCancelled(Exception):
    """A scan stopped before replacing the catalog contents."""


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
    ) -> ScanResult:
        source_dir = Path(source_dir).resolve()
        cache_dir = source_dir / ".dsb_cache"
        _check_cancelled(cancel_event)
        cache = CacheManager(cache_dir, self.metadata_reader)

        paths = self._find_images(source_dir, recursive, cancel_event)
        metadata_by_path = {}
        # ExifTool already batches at 100 files. Check cancellation between
        # batches instead of waiting for all metadata in a large folder.
        for offset in range(0, len(paths), 100):
            _check_cancelled(cancel_event)
            if progress_callback:
                progress_callback(0, len(paths), paths[offset])
            metadata_by_path.update(self.metadata_reader.read_batch(paths[offset:offset + 100]))
        pair_status = self._pair_status_by_path(paths)

        records: list[ImageRecord] = []
        for index, path in enumerate(paths, start=1):
            _check_cancelled(cancel_event)
            if progress_callback:
                progress_callback(index, len(paths), path)

            metadata = metadata_by_path.get(path)
            display_source, thumbnail_path, proxy_status = cache.ensure_display_assets(path)
            modified = datetime.fromtimestamp(path.stat().st_mtime)
            record = ImageRecord(
                id=None,
                file_path=path,
                file_ext=path.suffix.lower().lstrip("."),
                base_name=path.stem,
                media_type=media_type_for_path(path),
                pair_group_id=_pair_group_id(path),
                pair_status=pair_status.get(path, "unknown"),
                display_source=display_source,
                proxy_path=display_source if path.suffix.lower() not in {".jpg", ".jpeg"} else None,
                thumbnail_path=thumbnail_path,
                capture_datetime=metadata.capture_datetime if metadata else None,
                file_modified_datetime=modified,
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
            )
            records.append(record)

        _check_cancelled(cancel_event)
        # Do not touch the previous catalog until a complete scan is ready.
        catalog = Catalog(cache_dir / "catalog.sqlite")
        try:
            saved = catalog.upsert_images(records)
            catalog.remove_missing_under(source_dir, {record.file_path for record in records}, recursive=recursive)
            catalog.set_setting("last_opened_folder", str(source_dir))
        finally:
            catalog.close()
        return ScanResult(source_dir=source_dir, catalog_path=cache_dir / "catalog.sqlite", records=saved)

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
        return sorted(paths, key=lambda path: str(path).lower())

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
