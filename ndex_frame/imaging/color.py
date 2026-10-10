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


def _eight_bit(image: Image.Image) -> Image.Image:
    """Scale 16-bit grayscale to 8-bit instead of clipping at 255."""
    if image.mode.startswith("I"):
        return image.convert("I").point(lambda value: value * (1 / 257)).convert("L")
    return image


def _to_rgb(image: Image.Image) -> Image.Image:
    return _eight_bit(image).convert("RGB")


def _native_for_profile(image: Image.Image, profile: ImageCms.ImageCmsProfile) -> Image.Image:
    space = str(profile.profile.xcolor_space).strip()
    if (image.mode, space) in {("CMYK", "CMYK"), ("RGB", "RGB"), ("L", "GRAY")}:
        return image
    if image.mode.startswith("I") and space == "GRAY":
        return _eight_bit(image)
    return _to_rgb(image)


def prepare_master(path: Path, policy: MetadataPolicy) -> PreparedImage:
    with Image.open(path) as opened:
        source_exif = opened.getexif()
        oriented = ImageOps.exif_transpose(opened)
        source_icc = opened.info.get("icc_profile")
        warnings: list[str] = []

        if source_icc:
            try:
                source_profile = ImageCms.ImageCmsProfile(BytesIO(source_icc))
                target_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
                # Transform from the native mode when it matches the profile's
                # colour space (CMYK needs this); otherwise pre-convert.
                native = _native_for_profile(oriented, source_profile)
                rgb = ImageCms.profileToProfile(
                    native,
                    source_profile,
                    target_profile,
                    outputMode="RGB",
                )
            except (ImageCms.PyCMSError, OSError):
                rgb = _to_rgb(oriented)
                warnings.append("색상 프로필 변환 실패, 기본 변환 사용")
        else:
            rgb = _to_rgb(oriented)
            warnings.append("색상 프로필 없음")

        return PreparedImage(
            image=rgb.copy(),
            icc_bytes=srgb_profile_bytes(),
            exif_bytes=sanitize_exif(source_exif, policy),
            warnings=tuple(warnings),
        )
