from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageCms

from ndex_frame.core.models import MetadataPolicy
from ndex_frame.imaging.color import prepare_master, srgb_profile_bytes


ORIENTATION_TAG = 274
COPYRIGHT_TAG = 33432
DATETIME_TAG = 306
DATETIME_ORIGINAL_TAG = 36867
DATETIME_DIGITIZED_TAG = 36868
GPS_TAG = 34853


def image_with_profile(profile_name: str) -> tuple[Image.Image, bytes]:
    image = Image.new("RGB", (40, 30), (140, 90, 40))
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile(profile_name))
    return image, profile.tobytes()


def profile_description(profile_bytes: bytes) -> str:
    profile = ImageCms.ImageCmsProfile(BytesIO(profile_bytes))
    return ImageCms.getProfileDescription(profile).strip()


class ColorPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_directory.name)

        self.no_icc_path = self.temp_path / "no-icc.png"
        Image.new("RGBA", (40, 30), (140, 90, 40, 200)).save(self.no_icc_path)

        self.srgb_path = self.temp_path / "srgb.png"
        srgb_image, srgb_bytes = image_with_profile("sRGB")
        srgb_image.save(self.srgb_path, icc_profile=srgb_bytes)

        self.orientation_path = self.temp_path / "orientation.png"
        oriented_source = Image.new("RGB", (3, 2))
        oriented_source.putdata(
            [
                (255, 0, 0),
                (0, 255, 0),
                (0, 0, 255),
                (0, 255, 255),
                (255, 0, 255),
                (255, 255, 0),
            ]
        )
        orientation_exif = Image.Exif()
        orientation_exif[ORIENTATION_TAG] = 6
        oriented_source.save(self.orientation_path, exif=orientation_exif)

        self.exif_path = self.temp_path / "metadata.jpg"
        exif = Image.Exif()
        exif[DATETIME_TAG] = "2026:08:30 12:34:56"
        exif[DATETIME_ORIGINAL_TAG] = "2026:08:30 12:34:56"
        exif[DATETIME_DIGITIZED_TAG] = "2026:08:30 12:34:57"
        exif[COPYRIGHT_TAG] = "Joseph"
        exif[GPS_TAG] = {
            1: "N",
            2: (40.0, 0.0, 0.0),
            3: "W",
            4: (88.0, 0.0, 0.0),
        }
        Image.new("RGB", (20, 10), (60, 80, 100)).save(self.exif_path, exif=exif)

        self.lab_profile_path = self.temp_path / "invalid-lab-profile.jpg"
        lab_image, lab_bytes = image_with_profile("LAB")
        lab_image.save(self.lab_profile_path, icc_profile=lab_bytes)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_missing_icc_is_assumed_srgb_with_warning(self) -> None:
        prepared = prepare_master(self.no_icc_path, MetadataPolicy())

        self.assertEqual(prepared.image.mode, "RGB")
        self.assertIn("색상 프로필 없음", prepared.warnings)
        self.assertTrue(prepared.icc_bytes)
        self.assertIn("sRGB", profile_description(prepared.icc_bytes))

    def test_image_without_source_exif_can_be_saved_with_prepared_metadata(self) -> None:
        prepared = prepare_master(self.no_icc_path, MetadataPolicy())
        output_path = self.temp_path / "no-source-exif-prepared.jpg"

        prepared.image.save(
            output_path,
            format="JPEG",
            icc_profile=prepared.icc_bytes,
            exif=prepared.exif_bytes,
        )

        with Image.open(output_path) as reopened:
            self.assertTrue(reopened.info.get("icc_profile"))
            self.assertEqual(dict(reopened.getexif()), {})

    def test_tagged_srgb_source_is_prepared_without_missing_profile_warning(self) -> None:
        prepared = prepare_master(self.srgb_path, MetadataPolicy())

        self.assertEqual(prepared.image.getpixel((0, 0)), (140, 90, 40))
        self.assertEqual(prepared.warnings, ())
        self.assertIn("sRGB", profile_description(prepared.icc_bytes))

    def test_adobe_rgb_fixture_is_converted_to_srgb(self) -> None:
        fixture = Path(__file__).with_name("fixtures") / "adobe-rgb-master.jpg"
        with Image.open(fixture) as source:
            source_pixel = source.getpixel((31, 0))
            self.assertEqual(source.size, (32, 32))
            self.assertEqual(profile_description(source.info["icc_profile"]), "Adobe RGB (1998)")

        prepared = prepare_master(fixture, MetadataPolicy())

        self.assertEqual(prepared.image.size, (32, 32))
        self.assertEqual(prepared.warnings, ())
        self.assertIn("sRGB", profile_description(prepared.icc_bytes))
        self.assertGreater(prepared.image.getpixel((31, 0))[0], source_pixel[0] + 20)

    def test_exif_orientation_is_applied_and_cleared(self) -> None:
        prepared = prepare_master(self.orientation_path, MetadataPolicy())
        exif = Image.Exif()
        exif.load(prepared.exif_bytes)

        self.assertEqual(prepared.image.size, (2, 3))
        self.assertEqual(prepared.image.getpixel((0, 0)), (0, 255, 255))
        self.assertEqual(prepared.image.getpixel((1, 2)), (0, 0, 255))
        self.assertNotIn(ORIENTATION_TAG, exif)

    def test_gps_is_removed_but_capture_dates_and_copyright_remain(self) -> None:
        prepared = prepare_master(self.exif_path, MetadataPolicy(remove_gps=True))
        exif = Image.Exif()
        exif.load(prepared.exif_bytes)

        self.assertNotIn(GPS_TAG, exif)
        self.assertEqual(exif.get(DATETIME_TAG), "2026:08:30 12:34:56")
        self.assertEqual(exif.get(DATETIME_ORIGINAL_TAG), "2026:08:30 12:34:56")
        self.assertEqual(exif.get(DATETIME_DIGITIZED_TAG), "2026:08:30 12:34:57")
        self.assertEqual(exif.get(COPYRIGHT_TAG), "Joseph")

    def test_disabled_metadata_categories_are_not_preserved(self) -> None:
        policy = MetadataPolicy(preserve_capture=False, preserve_copyright=False, remove_gps=False)
        prepared = prepare_master(self.exif_path, policy)
        exif = Image.Exif()
        exif.load(prepared.exif_bytes)

        self.assertNotIn(DATETIME_TAG, exif)
        self.assertNotIn(DATETIME_ORIGINAL_TAG, exif)
        self.assertNotIn(DATETIME_DIGITIZED_TAG, exif)
        self.assertNotIn(COPYRIGHT_TAG, exif)
        self.assertIn(GPS_TAG, exif)

    def test_mismatched_non_rgb_profile_reports_transform_error(self) -> None:
        with self.assertRaises(ImageCms.PyCMSError):
            prepare_master(self.lab_profile_path, MetadataPolicy())

    def test_prepared_bytes_round_trip_with_icc_and_without_gps(self) -> None:
        prepared = prepare_master(self.exif_path, MetadataPolicy(remove_gps=True))
        output_path = self.temp_path / "prepared.jpg"
        prepared.image.save(
            output_path,
            format="JPEG",
            icc_profile=prepared.icc_bytes,
            exif=prepared.exif_bytes,
        )

        with Image.open(output_path) as reopened:
            self.assertTrue(reopened.info.get("icc_profile"))
            self.assertNotIn(GPS_TAG, reopened.getexif())
            self.assertEqual(reopened.getexif().get(COPYRIGHT_TAG), "Joseph")

    def test_srgb_profile_bytes_returns_a_reusable_rgb_profile(self) -> None:
        profile_bytes = srgb_profile_bytes()

        self.assertTrue(profile_bytes)
        self.assertIn("sRGB", profile_description(profile_bytes))


if __name__ == "__main__":
    unittest.main()
