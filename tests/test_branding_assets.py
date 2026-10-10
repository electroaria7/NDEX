from pathlib import Path
import unittest

from PIL import Image


BRANDING = Path(__file__).resolve().parents[1] / "assets" / "branding"
SIZES = (16, 24, 32, 48, 64, 128, 256)


class BrandingAssetsTests(unittest.TestCase):
    def test_window_icons_have_transparent_corners_and_a_solid_body(self):
        for size in SIZES:
            with self.subTest(size=size), Image.open(BRANDING / f"ndex_icon_{size}.png") as icon:
                self.assertEqual(icon.size, (size, size))
                self.assertEqual(icon.mode, "RGBA")
                for point in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
                    self.assertEqual(icon.getpixel(point)[3], 0)
                # The generated master retains a near-opaque antialiased alpha.
                self.assertGreaterEqual(icon.getpixel((size // 2, size // 2))[3], 250)

    def test_packaged_ico_preserves_each_native_png_size(self):
        with Image.open(BRANDING / "ndex_icon.ico") as icon:
            self.assertEqual(icon.ico.sizes(), {(size, size) for size in SIZES})
            for size in SIZES:
                with self.subTest(size=size), Image.open(BRANDING / f"ndex_icon_{size}.png") as png:
                    self.assertEqual(icon.ico.getimage((size, size)).tobytes(), png.tobytes())


if __name__ == "__main__":
    unittest.main()
