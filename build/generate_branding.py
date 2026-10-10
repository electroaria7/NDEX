"""Build Windows icon resources from the branding source artwork.

Run: python build/generate_branding.py

The small vector mark is used at 16/24 px. Larger sizes use the transparent
NDEX master. The ICO contains those exact PNGs, so Windows can select the
appropriate artwork instead of shrinking the detailed logo for title bars.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


BRANDING = Path(__file__).resolve().parents[1] / "assets" / "branding"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Could not encode the icon as PNG")
    return bytes(data)


def build_icons(directory: Path = BRANDING) -> None:
    master = QImage(str(directory / "ndex_icon_master.png"))
    if master.isNull() or not master.hasAlphaChannel():
        raise ValueError("The icon master must be a transparent PNG")
    if master.width() != master.height():
        raise ValueError("The icon master must be square")
    if master.pixelColor(0, 0).alpha() != 0:
        raise ValueError("The icon master must have transparent outside corners")
    small = QSvgRenderer(str(directory / "ndex_icon_small.svg"))
    if not small.isValid():
        raise ValueError("Could not load the small icon vector")

    entries: list[tuple[int, bytes]] = []
    for size in SIZES:
        if size <= 24:
            image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            small.render(painter)
            painter.end()
        else:
            image = master.scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        data = png_bytes(image)
        (directory / f"ndex_icon_{size}.png").write_bytes(data)
        entries.append((size, data))

    # Windows Vista and later accept PNG-compressed ICO image entries.
    offset = 6 + 16 * len(entries)
    header = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    for size, data in entries:
        header.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    (directory / "ndex_icon.ico").write_bytes(bytes(header) + b"".join(data for _, data in entries))


if __name__ == "__main__":
    build_icons()
    print(f"Built {len(SIZES)} PNG sizes and ndex_icon.ico in {BRANDING}")
