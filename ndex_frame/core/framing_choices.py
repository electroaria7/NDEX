from __future__ import annotations

import re

BACKGROUND_PRESETS: tuple[tuple[str, str], ...] = (
    ("White", "#FFFFFF"),
    ("Bright Gray", "#D0D0D0"),
    ("Medium Gray", "#808080"),
    ("Black", "#000000"),
)
RATIO_PRESETS: tuple[tuple[str, int, int], ...] = (
    ("3:4", 3, 4),
    ("4:5", 4, 5),
    ("1:1", 1, 1),
)
PHOTO_SIZE_PRESETS: tuple[int, ...] = (80, 90, 95)

_HEX3 = re.compile(r"^[0-9A-Fa-f]{3}$")
_HEX6 = re.compile(r"^[0-9A-Fa-f]{6}$")


def normalize_hex_color(value: str) -> str | None:
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if _HEX3.fullmatch(text):
        text = "".join(character * 2 for character in text)
    if _HEX6.fullmatch(text):
        return f"#{text.upper()}"
    return None
