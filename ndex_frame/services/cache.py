"""On-disk cache for small color-managed preview proxies."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from PIL import Image

from ndex_frame.core.models import MetadataPolicy, SourceItem
from ndex_frame.imaging.color import prepare_master


class CacheError(RuntimeError):
    """A cache problem that callers may handle by generating a direct preview."""


def cache_key(source: Path, max_edge: int) -> str:
    stat = source.stat()
    payload = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{max_edge}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PreviewCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def get_or_create(self, source: SourceItem, max_edge: int) -> Path:
        if max_edge <= 0:
            raise ValueError("max_edge must be positive.")

        try:
            key = cache_key(source.path, max_edge)
            output_path = self.root / f"{key}.jpg"
            if output_path.is_file():
                return output_path

            self.root.mkdir(parents=True, exist_ok=True)
            prepared = prepare_master(source.path, MetadataPolicy())
            image = prepared.image
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".tmp", prefix=f".{key}-", dir=self.root, delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
            try:
                image.save(
                    temporary_path,
                    format="JPEG",
                    quality=88,
                    icc_profile=prepared.icc_bytes,
                )
                os.replace(temporary_path, output_path)
            finally:
                temporary_path.unlink(missing_ok=True)
            return output_path
        except CacheError:
            raise
        except Exception as exc:
            raise CacheError(f"Failed to create preview cache for {source.path}") from exc
