from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from ..core.file_types import JPG_EXTENSIONS
from .metadata import MetadataReader, subprocess_no_window_options


class CacheManager:
    def __init__(self, cache_dir: Path, metadata_reader: MetadataReader | None = None):
        self.cache_dir = cache_dir
        self.thumbnail_dir = cache_dir / "thumbnails"
        self.preview_dir = cache_dir / "previews"
        self.metadata_reader = metadata_reader or MetadataReader()
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.preview_dir.mkdir(parents=True, exist_ok=True)

    def ensure_display_assets(self, image_path: Path) -> tuple[Path | None, Path | None, str]:
        if image_path.suffix.lower() in JPG_EXTENSIONS:
            thumbnail = self.ensure_jpg_thumbnail(image_path)
            return image_path, thumbnail, "not_required"

        proxy = self.ensure_raw_proxy(image_path)
        if proxy:
            thumbnail = self.ensure_jpg_thumbnail(proxy, source_key=image_path)
            return proxy, thumbnail, "embedded_preview"

        thumbnail = self.ensure_placeholder_thumbnail(image_path)
        return None, thumbnail, "failed"

    def ensure_jpg_thumbnail(self, image_path: Path, source_key: Path | None = None) -> Path | None:
        target = self.thumbnail_dir / f"{_safe_cache_stem(source_key or image_path)}_thumb.jpg"
        if _is_valid_image(target):
            return target

        try:
            with Image.open(image_path) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((420, 420))
                canvas = Image.new("RGB", (420, 420), "#1f2933")
                x = (420 - image.width) // 2
                y = (420 - image.height) // 2
                canvas.paste(image.convert("RGB"), (x, y))
                _save_atomic(canvas, target, quality=86)
                return target
        except OSError:
            return self.ensure_placeholder_thumbnail(source_key or image_path)

    def ensure_raw_proxy(self, raw_path: Path) -> Path | None:
        target = self.preview_dir / f"{_safe_cache_stem(raw_path)}_proxy.jpg"
        if _is_valid_image(target):
            return target
        extracted = self._extract_raw_preview(raw_path)
        if not extracted:
            return None
        fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=target.stem + ".", suffix=".tmp")
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(extracted)
            if not _is_valid_image(temp):
                return None
            os.replace(temp, target)
        except OSError:
            return None
        finally:
            temp.unlink(missing_ok=True)
        return target

    def ensure_placeholder_thumbnail(self, image_path: Path) -> Path:
        target = self.thumbnail_dir / f"{_safe_cache_stem(image_path)}_placeholder.jpg"
        if _is_valid_image(target):
            return target
        image = Image.new("RGB", (420, 420), "#202833")
        draw = ImageDraw.Draw(image)
        label = image_path.suffix.upper().lstrip(".") or "RAW"
        draw.rectangle((28, 28, 392, 392), outline="#5f6b7a", width=3)
        draw.text((44, 168), label, fill="#f2c14e")
        draw.text((44, 204), "preview unavailable", fill="#d7dee8")
        draw.text((44, 236), image_path.name[:34], fill="#9fb0c4")
        _save_atomic(image, target, quality=82)
        return target

    def _extract_raw_preview(self, raw_path: Path) -> bytes | None:
        exiftool = self.metadata_reader.exiftool_path
        if not exiftool:
            return None
        for tag in ("PreviewImage", "JpgFromRaw", "ThumbnailImage"):
            command = [str(exiftool), "-b", f"-{tag}", str(raw_path)]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    timeout=20,
                    check=False,
                    **subprocess_no_window_options(),
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if completed.returncode == 0 and completed.stdout and len(completed.stdout) > 200:
                return completed.stdout
        return None


def _is_valid_image(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with Image.open(path) as image:
            image.verify()
    except (OSError, SyntaxError, ValueError):
        return False
    return True


def _save_atomic(image: Image.Image, target: Path, quality: int) -> None:
    fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=target.stem + ".", suffix=".tmp")
    os.close(fd)
    temp = Path(temp_name)
    try:
        image.save(temp, "JPEG", quality=quality)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def _safe_cache_stem(path: Path) -> str:
    # The key includes mtime/size so a replaced or edited source gets a fresh cache entry.
    try:
        stat = path.stat()
        version = f"|{stat.st_mtime_ns}|{stat.st_size}"
    except OSError:
        version = ""
    digest = hashlib.sha1((str(path.resolve()) + version).encode("utf-8")).hexdigest()[:12]
    suffix = path.suffix.lower().lstrip(".") or "file"
    return f"{path.stem}_{suffix}_{digest}"
