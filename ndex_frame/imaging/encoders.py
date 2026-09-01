from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from PIL import Image

from ndex_frame.core.models import OutputProfile
from ndex_frame.imaging.color import PreparedImage


_PILLOW_FORMATS = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}


def verify_output(path: Path, profile: OutputProfile, expected_size: tuple[int, int]) -> None:
    """Raise when a completed output is not the requested format or size."""
    expected_format = _PILLOW_FORMATS[profile.format]
    with Image.open(path) as opened:
        if opened.format != expected_format:
            raise ValueError(f"Expected {expected_format} output, received {opened.format}.")
        if opened.size != expected_size:
            raise ValueError(f"Expected {expected_size} output, received {opened.size}.")
        opened.verify()


def save_output_atomic(
    rendered: Image.Image,
    destination: Path,
    profile: OutputProfile,
    prepared: PreparedImage,
    *,
    pre_rename_hook: Callable[[], None] | None = None,
) -> Path:
    """Encode an output once, then move its verified temporary file without replacement."""
    if destination.exists():
        raise FileExistsError(destination)

    temporary = destination.parent / f".{destination.name}.{uuid4().hex}.ndex_tmp"
    temporary_owned = False
    try:
        with temporary.open("xb") as handle:
            temporary_owned = True
            if profile.format == "jpeg":
                rendered.save(
                    handle,
                    format="JPEG",
                    quality=profile.quality,
                    subsampling=0,
                    optimize=True,
                    icc_profile=prepared.icc_bytes,
                    exif=prepared.exif_bytes,
                )
            elif profile.format == "png":
                rendered.save(
                    handle,
                    format="PNG",
                    optimize=True,
                    icc_profile=prepared.icc_bytes,
                    exif=prepared.exif_bytes,
                )
            elif profile.format == "webp":
                rendered.save(
                    handle,
                    format="WEBP",
                    quality=profile.quality,
                    method=6,
                    icc_profile=prepared.icc_bytes,
                    exif=prepared.exif_bytes,
                )
            else:
                raise ValueError(f"Unsupported output format: {profile.format}")
            handle.flush()
            os.fsync(handle.fileno())

        verify_output(temporary, profile, rendered.size)
        if destination.exists():
            raise FileExistsError(destination)
        if pre_rename_hook is not None:
            pre_rename_hook()
        os.rename(temporary, destination)
        return destination
    except BaseException:
        if temporary_owned and temporary.exists():
            temporary.unlink()
        raise
