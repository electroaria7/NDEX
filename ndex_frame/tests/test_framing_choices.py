from __future__ import annotations

import unittest

from ndex_frame.core.framing_choices import (
    BACKGROUND_PRESETS,
    PHOTO_SIZE_PRESETS,
    normalize_hex_color,
)


class FramingChoicesTests(unittest.TestCase):
    def test_background_presets_include_white_and_grays(self) -> None:
        names = [name for name, _color in BACKGROUND_PRESETS]
        self.assertEqual(names, ["White", "Bright Gray", "Medium Gray"])
        colors = dict(BACKGROUND_PRESETS)
        self.assertEqual(colors["White"], "#FFFFFF")
        self.assertEqual(colors["Bright Gray"], "#D0D0D0")
        self.assertEqual(colors["Medium Gray"], "#808080")

    def test_photo_size_presets_are_eighty_ninety_ninety_five(self) -> None:
        self.assertEqual(PHOTO_SIZE_PRESETS, (80, 90, 95))

    def test_normalize_hex_color_accepts_short_and_long_forms(self) -> None:
        self.assertEqual(normalize_hex_color("#fff"), "#FFFFFF")
        self.assertEqual(normalize_hex_color("808080"), "#808080")
        self.assertIsNone(normalize_hex_color("red"))
        self.assertIsNone(normalize_hex_color("#GG0000"))


if __name__ == "__main__":
    unittest.main()
