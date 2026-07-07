"""Read star ratings from selected JPG files.

Rating sources, in priority order:
1. XMP sidecar next to the JPG (``photo.xmp`` — written by NDEX or Lightroom).
2. Embedded EXIF ``Rating`` tag (0x4746 — written by Windows Explorer and
   some editors), read via Pillow when available.
3. Embedded XMP packet inside the JPG (APP1 segment), scanned as text.

Returns ``None`` when no rating is found, so callers can fall back to a
default. Never modifies the JPG.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

XMP_NS = "http://ns.adobe.com/xap/1.0/"
EXIF_RATING_TAG = 0x4746
_EMBEDDED_XMP_PATTERN = re.compile(rb'xmp:Rating\s*=\s*"(-?\d+)"')
_EMBEDDED_XMP_ELEMENT_PATTERN = re.compile(rb"<xmp:Rating>\s*(-?\d+)\s*</xmp:Rating>")
_SCAN_BYTES = 262144


def read_jpg_rating(jpg_path: Path) -> int | None:
    """Return the 0-5 star rating for a JPG, or None if not found."""
    rating = _from_sidecar(jpg_path)
    if rating is None:
        rating = _from_exif(jpg_path)
    if rating is None:
        rating = _from_embedded_xmp(jpg_path)
    if rating is None:
        return None
    return max(0, min(5, rating))


def _from_sidecar(jpg_path: Path) -> int | None:
    sidecar = jpg_path.with_suffix(".xmp")
    if not sidecar.is_file():
        return None
    try:
        root = ET.parse(sidecar).getroot()
    except (ET.ParseError, OSError):
        return None

    for element in root.iter():
        value = element.attrib.get(f"{{{XMP_NS}}}Rating")
        if value is not None:
            return _to_int(value)
        if element.tag == f"{{{XMP_NS}}}Rating" and element.text:
            return _to_int(element.text)
    return None


def _from_exif(jpg_path: Path) -> int | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(jpg_path) as image:
            value = image.getexif().get(EXIF_RATING_TAG)
    except (OSError, ValueError):
        return None
    if value is None:
        return None
    return _to_int(value)


def _from_embedded_xmp(jpg_path: Path) -> int | None:
    try:
        with jpg_path.open("rb") as handle:
            head = handle.read(_SCAN_BYTES)
    except OSError:
        return None
    match = _EMBEDDED_XMP_PATTERN.search(head) or _EMBEDDED_XMP_ELEMENT_PATTERN.search(head)
    if match:
        return _to_int(match.group(1))
    return None


def _to_int(value) -> int | None:
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
