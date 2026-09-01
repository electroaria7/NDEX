from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, JpegImagePlugin

from ndex_frame.core.models import MetadataPolicy, OutputProfile, OutputSizing
from ndex_frame.imaging.color import PreparedImage, srgb_profile_bytes
from ndex_frame.imaging.encoders import save_output_atomic, verify_output


class EncoderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.output_directory = Path(self.temp_directory.name)
        self.destination = self.output_directory / "output.jpg"
        self.image = Image.new("RGB", (1080, 1440), (20, 40, 60))
        exif = Image.Exif()
        exif[33432] = "Joseph"
        self.prepared = PreparedImage(self.image.copy(), srgb_profile_bytes(), exif.tobytes(), ())
        self.jpeg_profile = self.make_profile("jpeg")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def make_profile(self, format_name: str) -> OutputProfile:
        return OutputProfile(
            id=f"test.{format_name}",
            name=f"Test {format_name}",
            version=1,
            sizing=OutputSizing("fixed_dimensions", width=1080, height=1440),
            format=format_name,  # type: ignore[arg-type]
            quality=95,
            chroma_subsampling="4:4:4",
            color_space="sRGB",
            embed_icc=True,
            metadata=MetadataPolicy(),
        )

    def test_jpeg_is_444_and_contains_prepared_metadata(self) -> None:
        result = save_output_atomic(self.image, self.destination, self.jpeg_profile, self.prepared)

        with Image.open(result) as reopened:
            self.assertEqual(reopened.format, "JPEG")
            self.assertEqual(reopened.size, (1080, 1440))
            self.assertTrue(reopened.info.get("icc_profile"))
            self.assertEqual(reopened.getexif().get(33432), "Joseph")
            self.assertEqual(JpegImagePlugin.get_sampling(reopened), 0)

    def test_png_and_webp_contain_prepared_metadata(self) -> None:
        for format_name, extension, pillow_format in (("png", ".png", "PNG"), ("webp", ".webp", "WEBP")):
            destination = self.output_directory / f"output{extension}"
            result = save_output_atomic(self.image, destination, self.make_profile(format_name), self.prepared)

            with self.subTest(format_name=format_name), Image.open(result) as reopened:
                self.assertEqual(reopened.format, pillow_format)
                self.assertEqual(reopened.size, (1080, 1440))
                self.assertTrue(reopened.info.get("icc_profile"))
                self.assertEqual(reopened.getexif().get(33432), "Joseph")

    def test_existing_destination_is_never_replaced(self) -> None:
        self.destination.write_bytes(b"existing")

        with self.assertRaises(FileExistsError):
            save_output_atomic(self.image, self.destination, self.jpeg_profile, self.prepared)

        self.assertEqual(self.destination.read_bytes(), b"existing")
        self.assertEqual(list(self.output_directory.glob("*.ndex_tmp")), [])

    def test_temporary_collision_preserves_file_not_owned_by_this_save(self) -> None:
        temporary = self.output_directory / ".output.jpg.collision.ndex_tmp"
        temporary.write_bytes(b"pre-existing temporary")

        with patch("ndex_frame.imaging.encoders.uuid4", return_value=SimpleNamespace(hex="collision")):
            with self.assertRaises(FileExistsError):
                save_output_atomic(self.image, self.destination, self.jpeg_profile, self.prepared)

        self.assertEqual(temporary.read_bytes(), b"pre-existing temporary")

    @unittest.skipUnless(os.name == "nt", "Windows rename semantics are required for this race test")
    def test_destination_created_immediately_before_rename_is_not_replaced(self) -> None:
        def create_destination() -> None:
            self.destination.write_bytes(b"raced")

        with self.assertRaises(FileExistsError):
            save_output_atomic(
                self.image,
                self.destination,
                self.jpeg_profile,
                self.prepared,
                pre_rename_hook=create_destination,
            )

        self.assertEqual(self.destination.read_bytes(), b"raced")
        self.assertEqual(list(self.output_directory.glob("*.ndex_tmp")), [])

    def test_verify_output_rejects_wrong_format_and_dimensions(self) -> None:
        result = save_output_atomic(self.image, self.destination, self.jpeg_profile, self.prepared)

        with self.assertRaises(ValueError):
            verify_output(result, self.make_profile("png"), (1080, 1440))
        with self.assertRaises(ValueError):
            verify_output(result, self.jpeg_profile, (1, 1))


if __name__ == "__main__":
    unittest.main()
