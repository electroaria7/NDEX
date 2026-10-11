"""Small on-disk thumbnails for the Images list.

Much lighter than ``PreviewCache``: JPEGs are decoded at reduced size
(``Image.draft``) and the result is a tiny file keyed by path + size + mtime +
edge, so a changed photo gets a fresh thumbnail and a list of hundreds opens
quickly the second time.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageCms, ImageOps



class ThumbnailError(RuntimeError):
    """The thumbnail could not be produced; the list keeps its placeholder."""


def thumbnail_key(source: Path, edge: int) -> str:
    stat = source.stat()
    payload = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{edge}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ThumbnailCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, source: Path, edge: int) -> Path:
        return self.root / f"{thumbnail_key(source, edge)}.png"

    def get_or_create(self, source: Path, edge: int) -> Path:
        """Return a PNG no larger than ``edge`` pixels on its long side."""
        if edge <= 0:
            raise ValueError("edge must be positive.")
        try:
            output = self.path_for(source, edge)
            if output.is_file():
                return output
            self.root.mkdir(parents=True, exist_ok=True)
            image = _render(source, edge)
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".tmp", prefix=f".{output.stem}-", dir=self.root, delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
            try:
                image.save(temporary_path, format="PNG")
                os.replace(temporary_path, output)
            finally:
                temporary_path.unlink(missing_ok=True)
            return output
        except Exception as error:
            raise ThumbnailError(f"Could not make a thumbnail for {source}") from error


def _render(source: Path, edge: int) -> Image.Image:
    with Image.open(source) as opened:
        if opened.format == "JPEG":
            # Let the decoder skip work: it picks a scale >= the request.
            opened.draft("RGB", (edge * 2, edge * 2))
        icc = opened.info.get("icc_profile")
        oriented = ImageOps.exif_transpose(opened)
        oriented.thumbnail((edge, edge), Image.Resampling.BILINEAR)
        if oriented.mode in ("I;16", "I;16B", "I;16L", "I"):
            oriented = oriented.point(lambda value: value * (1 / 257)).convert("L")
        if icc and oriented.mode in ("RGB", "L", "RGBA"):
            try:
                profile = ImageCms.ImageCmsProfile(BytesIO(icc))
                target = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
                oriented = ImageCms.profileToProfile(
                    oriented.convert("RGB"), profile, target, outputMode="RGB"
                )
            except (ImageCms.PyCMSError, OSError, ValueError):
                pass
        return oriented.convert("RGBA" if "A" in oriented.mode else "RGB").copy()
