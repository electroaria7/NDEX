from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .app_paths import find_bundled_exiftool

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None


class MetadataExtractor:
    DEFAULT_BATCH_SIZE = 50
    DEFAULT_TIMEOUT_SECONDS = 60

    def __init__(
        self,
        exiftool_path: str | None = None,
        batch_size: int | None = None,
        timeout_seconds: int | None = None,
    ):
        self.exiftool_path = self._resolve_exiftool_path(exiftool_path)
        self.batch_size = max(1, int(batch_size or self.DEFAULT_BATCH_SIZE))
        self.timeout_seconds = max(1, int(timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS))

    @classmethod
    def from_settings(cls, settings: dict, exiftool_path: str | None = None) -> "MetadataExtractor":
        return cls(
            exiftool_path=exiftool_path,
            batch_size=settings.get("metadata_batch_size"),
            timeout_seconds=settings.get("metadata_batch_timeout_seconds"),
        )

    def get_capture_datetime(self, file_path: Path, logger=None) -> tuple[datetime, str, bool]:
        return self.get_capture_datetimes([file_path], logger=logger)[file_path]

    def get_capture_datetimes(
        self,
        file_paths: Iterable[Path],
        logger=None,
    ) -> dict[Path, tuple[datetime, str, bool]]:
        paths = [Path(path) for path in file_paths]
        results: dict[Path, tuple[datetime, str, bool]] = {}

        if not self.exiftool_path and logger:
            logger.warn("ExifTool was not found. RAW metadata will use fallback dates when needed.")

        exiftool_dates = self._from_exiftool_batch(paths, logger=logger)
        for file_path, capture_time in exiftool_dates.items():
            results[file_path] = (capture_time, "exiftool", False)

        for file_path in paths:
            if file_path in results:
                continue

            capture_time = self._from_pillow(file_path)
            if capture_time:
                results[file_path] = (capture_time, "pillow", False)
                continue

            fallback = datetime.fromtimestamp(file_path.stat().st_mtime)
            if logger:
                logger.warn(
                    f"Metadata read failed for {file_path.name}. "
                    "Using file modified time as fallback."
                )
            results[file_path] = (fallback, "modified_time", True)
        return results

    def _get_capture_datetime_slow(self, file_path: Path, logger=None) -> tuple[datetime, str, bool]:
        capture_time = self._from_pillow(file_path)
        if capture_time:
            return capture_time, "pillow", False

        capture_time = self._from_exiftool(file_path)
        if capture_time:
            return capture_time, "exiftool", False

        fallback = datetime.fromtimestamp(file_path.stat().st_mtime)
        if logger:
            logger.warn(
                f"Metadata read failed for {file_path.name}. "
                "Using file modified time as fallback."
            )
        return fallback, "modified_time", True

    def _resolve_exiftool_path(self, explicit_path: str | None) -> str | None:
        if explicit_path and Path(explicit_path).exists():
            return explicit_path

        bundled = find_bundled_exiftool()
        if bundled:
            return str(bundled)

        for candidate in ("exiftool.exe", "exiftool"):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return None

    def _from_exiftool(self, file_path: Path) -> datetime | None:
        return self._from_exiftool_batch([file_path]).get(file_path)

    def _from_exiftool_batch(self, file_paths: Iterable[Path], logger=None) -> dict[Path, datetime]:
        paths = [Path(path) for path in file_paths]
        if not paths or not self.exiftool_path:
            return {}

        dates: dict[Path, datetime] = {}
        for chunk in self._chunk_paths(paths, chunk_size=self.batch_size):
            dates.update(self._from_exiftool_chunk_with_retry(chunk, logger=logger))
        return dates

    def _from_exiftool_chunk_with_retry(self, file_paths: list[Path], logger=None) -> dict[Path, datetime]:
        dates, error = self._from_exiftool_chunk(file_paths)
        if dates or not error:
            return dates

        if len(file_paths) == 1:
            if logger:
                logger.warn(f"ExifTool metadata read failed for {file_paths[0].name}: {error}")
            return {}

        if logger:
            logger.warn(
                f"ExifTool batch read failed for {len(file_paths)} files: {error}. "
                "Retrying with smaller batches."
            )

        midpoint = max(1, len(file_paths) // 2)
        retried_dates: dict[Path, datetime] = {}
        retried_dates.update(self._from_exiftool_chunk_with_retry(file_paths[:midpoint], logger=logger))
        retried_dates.update(self._from_exiftool_chunk_with_retry(file_paths[midpoint:], logger=logger))
        return retried_dates

    def _from_exiftool_chunk(self, file_paths: list[Path]) -> tuple[dict[Path, datetime], str | None]:
        if not self.exiftool_path:
            return {}, "ExifTool path is not configured"

        command = [
            self.exiftool_path,
            "-j",
            "-DateTimeOriginal",
            "-CreateDate",
            "-ModifyDate",
            "-DateCreated",
            "-MediaCreateDate",
            "-TrackCreateDate",
            "-d",
            "%Y-%m-%d %H:%M:%S",
            *[str(path) for path in file_paths],
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                **self._subprocess_no_window_options(),
            )
        except subprocess.TimeoutExpired:
            return {}, f"timed out after {self.timeout_seconds} seconds"
        except OSError as exc:
            return {}, str(exc)
        except subprocess.SubprocessError as exc:
            return {}, str(exc)

        if result.returncode != 0 or not result.stdout.strip():
            detail = result.stderr.strip() or f"return code {result.returncode}"
            return {}, detail

        try:
            records = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            return {}, "ExifTool returned invalid JSON"

        input_lookup = {path.resolve(): path for path in file_paths}
        dates: dict[Path, datetime] = {}
        for record in records:
            source = record.get("SourceFile")
            if not source:
                continue

            parsed = None
            for key in (
                "DateTimeOriginal",
                "CreateDate",
                "ModifyDate",
                "DateCreated",
                "MediaCreateDate",
                "TrackCreateDate",
            ):
                parsed = self._parse_datetime(record.get(key))
                if parsed:
                    break
            if parsed:
                source_path = Path(source)
                dates[input_lookup.get(source_path.resolve(), source_path)] = parsed
        return dates, None

    @staticmethod
    def _chunk_paths(paths: list[Path], chunk_size: int) -> Iterable[list[Path]]:
        for index in range(0, len(paths), chunk_size):
            yield paths[index:index + chunk_size]

    @staticmethod
    def _subprocess_no_window_options() -> dict:
        options = {}
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if create_no_window:
            options["creationflags"] = create_no_window

        startupinfo_class = getattr(subprocess, "STARTUPINFO", None)
        if startupinfo_class:
            startupinfo = startupinfo_class()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
            startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            options["startupinfo"] = startupinfo
        return options

    def _from_pillow(self, file_path: Path) -> datetime | None:
        if Image is None:
            return None
        if file_path.suffix.lower() not in {".jpg", ".jpeg"}:
            return None

        try:
            with Image.open(file_path) as image:
                exif = image.getexif()
        except OSError:
            return None

        for tag_id in (36867, 306):
            parsed = self._parse_datetime(exif.get(tag_id))
            if parsed:
                return parsed
        return None

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not value or not isinstance(value, str):
            return None

        cleaned = value.strip().replace("T", " ")
        formats = (
            "%Y:%m:%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S%z",
        )
        for date_format in formats:
            try:
                return datetime.strptime(cleaned, date_format)
            except ValueError:
                continue
        return None
