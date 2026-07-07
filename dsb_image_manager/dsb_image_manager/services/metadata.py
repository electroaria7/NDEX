from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image

from ..core.file_types import JPG_EXTENSIONS
from ..core.models import ImageMetadata


class MetadataReader:
    def __init__(self, exiftool_path: Path | None = None):
        self.exiftool_path = self._resolve_exiftool(exiftool_path)

    def read_batch(self, paths: Iterable[Path]) -> dict[Path, ImageMetadata]:
        image_paths = [Path(path) for path in paths]
        results = self._read_with_exiftool(image_paths)
        for path in image_paths:
            if path not in results:
                results[path] = self._read_with_pillow(path)
        return results

    def _read_with_exiftool(self, paths: list[Path]) -> dict[Path, ImageMetadata]:
        if not paths or not self.exiftool_path:
            return {}

        results: dict[Path, ImageMetadata] = {}
        for chunk in _chunks(paths, 100):
            results.update(self._read_exiftool_chunk(chunk))
        return results

    def _read_exiftool_chunk(self, paths: list[Path]) -> dict[Path, ImageMetadata]:
        assert self.exiftool_path is not None
        command = [
            str(self.exiftool_path),
            "-api",
            "largefilesupport=1",
            "-m",
            "-j",
            "-SubSecDateTimeOriginal",
            "-DateTimeOriginal",
            "-CreateDate",
            "-MediaCreateDate",
            "-TrackCreateDate",
            "-ModifyDate",
            "-Make",
            "-Model",
            "-CameraModelName",
            "-LensModel",
            "-Lens",
            "-LensID",
            "-LensType",
            "-FocalLength",
            "-ExposureTime",
            "-ShutterSpeed",
            "-ShutterSpeedValue",
            "-FNumber",
            "-Aperture",
            "-ApertureValue",
            "-ISO",
            "-ISOSpeedRatings",
            "-RecommendedExposureIndex",
            "-ExposureCompensation",
            "-WhiteBalance",
            "-ColorSpace",
            "-ColorRepresentation",
            "-ImageWidth",
            "-ImageHeight",
            "-ExifImageWidth",
            "-ExifImageHeight",
            "-ImageSize",
            "-GPSLatitude",
            "-GPSLongitude",
            "-FileSize",
            "-d",
            "%Y-%m-%d %H:%M:%S",
            *[str(path) for path in paths],
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                **subprocess_no_window_options(),
            )
        except (OSError, subprocess.SubprocessError):
            return {}

        # ExifTool can return a non-zero status when one file in a batch has a
        # minor warning. If JSON was still emitted, keep the usable rows.
        if not completed.stdout.strip():
            return {}

        try:
            rows = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {}

        lookup = {path.resolve(): path for path in paths}
        results: dict[Path, ImageMetadata] = {}
        for row in rows:
            source = row.get("SourceFile")
            if not source:
                continue
            source_path = Path(source).resolve()
            key = lookup.get(source_path, Path(source))
            results[key] = metadata_from_exiftool_row(row)
        return results

    def _read_with_pillow(self, path: Path) -> ImageMetadata:
        metadata = ImageMetadata()
        if path.suffix.lower() not in JPG_EXTENSIONS:
            return metadata
        try:
            with Image.open(path) as image:
                metadata.width, metadata.height = image.size
                metadata.color_space = image.info.get("icc_profile") and "ICC profile" or image.mode
                exif = image.getexif()
        except OSError:
            return metadata

        metadata.capture_datetime = _parse_datetime(exif.get(36867)) or _parse_datetime(exif.get(306))
        metadata.has_exif = bool(exif)
        return metadata

    @staticmethod
    def _resolve_exiftool(explicit: Path | None) -> Path | None:
        if explicit and explicit.exists():
            return explicit

        bundled_root = Path(getattr(sys, "_MEIPASS", Path.cwd()))
        candidates = [
            bundled_root / "vendor" / "exiftool" / "exiftool.exe",
            Path.cwd() / "vendor" / "exiftool" / "exiftool.exe",
            Path.cwd().parent / "vendor" / "exiftool" / "exiftool.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        found = shutil.which("exiftool.exe") or shutil.which("exiftool")
        return Path(found) if found else None


def subprocess_no_window_options() -> dict:
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


def _parse_datetime(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip().replace("T", " ")
    cleaned = re.sub(r"([+-]\d{2}:?\d{2}|Z)$", "", cleaned)
    cleaned = cleaned.split(".", 1)[0]
    for date_format in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z"):
        try:
            parsed = datetime.strptime(cleaned, date_format)
            return parsed.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def metadata_from_exiftool_row(row: dict) -> ImageMetadata:
    width, height = _dimensions_from_row(row)
    return ImageMetadata(
        capture_datetime=_first_datetime(
            row,
            "SubSecDateTimeOriginal",
            "DateTimeOriginal",
            "CreateDate",
            "MediaCreateDate",
            "TrackCreateDate",
            "ModifyDate",
        ),
        camera_model=_first_text(row, "Model", "CameraModelName"),
        lens_model=_first_text(row, "LensModel", "Lens", "LensID", "LensType"),
        focal_length=_first_text(row, "FocalLength"),
        exposure_time=_first_text(row, "ExposureTime", "ShutterSpeed", "ShutterSpeedValue"),
        aperture=_normalize_aperture(_first_text(row, "FNumber", "Aperture", "ApertureValue")),
        iso=_first_text(row, "ISO", "ISOSpeedRatings", "RecommendedExposureIndex"),
        exposure_compensation=_first_text(row, "ExposureCompensation"),
        white_balance=_first_text(row, "WhiteBalance"),
        color_space=_first_text(row, "ColorSpace", "ColorRepresentation"),
        width=width,
        height=height,
        file_size=_first_text(row, "FileSize"),
        gps=_join_gps(row.get("GPSLatitude"), row.get("GPSLongitude")),
        has_exif=_row_has_metadata(row),
    )


def _first_text(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _first_datetime(row: dict, *keys: str) -> datetime | None:
    for key in keys:
        parsed = _parse_datetime(row.get(key))
        if parsed:
            return parsed
    return None


def _dimensions_from_row(row: dict) -> tuple[int | None, int | None]:
    width = _int_or_none(row.get("ImageWidth")) or _int_or_none(row.get("ExifImageWidth"))
    height = _int_or_none(row.get("ImageHeight")) or _int_or_none(row.get("ExifImageHeight"))
    if width and height:
        return width, height

    image_size = str(row.get("ImageSize", "") or "")
    if "x" in image_size:
        left, right = image_size.lower().split("x", 1)
        return _int_or_none(left.strip()), _int_or_none(right.strip())
    return width, height


def _normalize_aperture(value: str) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    return cleaned[2:] if cleaned.lower().startswith("f/") else cleaned


def _row_has_metadata(row: dict) -> bool:
    ignored = {"SourceFile", "ExifToolVersion", "FileName", "Directory", "FilePermissions"}
    return any(value not in (None, "") for key, value in row.items() if key not in ignored)


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _join_gps(latitude: object, longitude: object) -> str:
    if latitude and longitude:
        return f"{latitude}, {longitude}"
    return ""


def _chunks(items: list[Path], size: int):
    for index in range(0, len(items), size):
        yield items[index:index + size]
