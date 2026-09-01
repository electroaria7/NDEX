from __future__ import annotations

import unittest

from PIL import Image

from ndex_frame.core.models import RenderPlan
from ndex_frame.imaging.color import PreparedImage
from ndex_frame.imaging.renderer import render


class RendererTests(unittest.TestCase):
    def test_renderer_places_photo_on_white_canvas(self) -> None:
        prepared = PreparedImage(Image.new("RGB", (6, 4), "red"), b"icc", b"", ())
        plan = RenderPlan(12, 16, 12, 8, 0, 4)

        rendered = render(prepared, plan, "#FFFFFF")

        self.assertEqual(rendered.size, (12, 16))
        self.assertEqual(rendered.mode, "RGB")
        self.assertEqual(rendered.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(rendered.getpixel((6, 8)), (255, 0, 0))


if __name__ == "__main__":
    unittest.main()
