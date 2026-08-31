import unittest
from pathlib import Path

from ndex_frame.core.models import AspectRatio, FramePreset, ImageOverride, OutputSizing


class ModelTests(unittest.TestCase):
    def test_ratio_rejects_non_positive_parts(self) -> None:
        with self.assertRaises(ValueError):
            AspectRatio(0, 4)

    def test_frame_scale_is_limited_to_fit_range(self) -> None:
        with self.assertRaises(ValueError):
            FramePreset("custom.bad", "Bad", 1, AspectRatio(3, 4), "#FFFFFF", 1.01, 0.0, 0.0, False)

    def test_fixed_width_requires_positive_width(self) -> None:
        with self.assertRaises(ValueError):
            OutputSizing(mode="fixed_width", width=0)

    def test_override_is_source_specific(self) -> None:
        override = ImageOverride(Path("IMG_001.jpg"), 0.9, 0.1, -0.2)
        self.assertEqual(override.photo_scale, 0.9)

    def test_override_scale_rejects_below_fit_range(self) -> None:
        with self.assertRaises(ValueError):
            ImageOverride(Path("IMG_001.jpg"), 0.09, 0.0, 0.0)

    def test_override_scale_rejects_above_fit_range(self) -> None:
        with self.assertRaises(ValueError):
            ImageOverride(Path("IMG_001.jpg"), 1.01, 0.0, 0.0)


if __name__ == "__main__":
    unittest.main()
