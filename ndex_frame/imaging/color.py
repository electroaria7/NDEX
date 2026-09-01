from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageCms, ImageOps
from PIL.ExifTags import IFD

from ndex_frame.core.models import MetadataPolicy

_ORIENTATION_TAG = 274
_COPYRIGHT_TAG = 33432
_GPS_TAG = 34853
_CAPTURE_DATE_TAGS = (306, 36867, 36868)


@dataclass(slots=True)
class PreparedImage:
    image: Image.Image
    icc_bytes: bytes
    exif_bytes: bytes
    warnings: tuple[str, ...]


def srgb_profile_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def sanitize_exif(source_exif: Image.Exif, policy: MetadataPolicy) -> bytes:
    sanitized = Image.Exif()
    sanitized.load(source_exif.tobytes())

    sanitized.pop(_ORIENTATION_TAG, None)
    if not policy.preserve_capture:
        for tag in _CAPTURE_DATE_TAGS:
            sanitized.pop(tag, None)
        exif_ifd = sanitized.get_ifd(IFD.Exif)
        for tag in _CAPTURE_DATE_TAGS:
            exif_ifd.pop(tag, None)
    if not policy.preserve_copyright:
        sanitized.pop(_COPYRIGHT_TAG, None)
    if policy.remove_gps:
        sanitized.pop(_GPS_TAG, None)

    return sanitized.tobytes()


def prepare_master(path: Path, policy: MetadataPolicy) -> PreparedImage:
    with Image.open(path) as opened:
        source_exif = opened.getexif()
        oriented = ImageOps.exif_transpose(opened)
        source_icc = opened.info.get("icc_profile")
        warnings: list[str] = []

        if source_icc:
            source_profile = ImageCms.ImageCmsProfile(BytesIO(source_icc))
            target_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
            rgb = ImageCms.profileToProfile(
                oriented.convert("RGB"),
                source_profile,
                target_profile,
                outputMode="RGB",
            )
        else:
            rgb = oriented.convert("RGB")
            warnings.append("색상 프로필 없음")

        return PreparedImage(
            image=rgb.copy(),
            icc_bytes=srgb_profile_bytes(),
            exif_bytes=sanitize_exif(source_exif, policy),
            warnings=tuple(warnings),
        )
