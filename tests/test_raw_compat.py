"""RAW compatibility: shared extension table, sidecar names, preview fallbacks.

The optional integration test runs against real files when NDEX_RAW_SAMPLES
points to a folder of RAW samples (see docs/RAW_Compatibility.md).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from dsb_image_manager.dsb_image_manager.core import file_types as im_file_types
from dsb_image_manager.dsb_image_manager.services import cache as cache_module
from dsb_image_manager.dsb_image_manager.services.cache import CacheManager
from ndex_auto_selector.ndex_auto_selector.services.selector import AutoSelectorService
from ndex_auto_selector.ndex_auto_selector.services import selector as selector_module
from ndex_common import xmp as xmp_module
from ndex_common.raw_formats import RAW_EXTENSIONS, RAW_FORMATS, extensions_for_brand, raw_format_for
from ndex_common.xmp import sidecar_path_for
from src import file_types as one_types
from src.metadata import MetadataExtractor

EXPECTED = {".cr3", ".cr2", ".crw", ".arw", ".srf", ".sr2", ".nef", ".nrw", ".dng"}


def jpeg_bytes(size=(40, 20), orientation: int | None = None) -> bytes:
    image = Image.new("RGB", size, "#336699")
    buffer = io.BytesIO()
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        image.save(buffer, "JPEG", exif=exif)
    else:
        image.save(buffer, "JPEG")
    return buffer.getvalue()


class ExtensionTableTests(unittest.TestCase):
    def test_table_covers_required_formats(self) -> None:
        self.assertEqual(set(RAW_EXTENSIONS), EXPECTED)
        for extension, fmt in RAW_FORMATS.items():
            self.assertEqual(extension, extension.lower())
            self.assertTrue(fmt.brand and fmt.name)

    def test_every_app_uses_the_shared_table(self) -> None:
        self.assertEqual(set(im_file_types.RAW_EXTENSIONS), EXPECTED)
        self.assertEqual(set(selector_module.RAW_EXTENSIONS), EXPECTED)
        self.assertEqual(set(xmp_module.RAW_EXTENSIONS), EXPECTED)

    def test_ndex_one_types_and_brands(self) -> None:
        expected = {
            ".cr3": ("cr3", "canon"), ".cr2": ("cr2", "canon"), ".crw": ("crw", "canon"),
            ".arw": ("arw", "sony"), ".srf": ("srf", "sony"), ".sr2": ("sr2", "sony"),
            ".nef": ("nef", "nikon"), ".nrw": ("nrw", "nikon"),
        }
        for extension, (file_type, brand) in expected.items():
            for name in (f"IMG_0001{extension}", f"IMG_0001{extension.upper()}"):
                self.assertEqual(one_types.get_file_type_for_path(Path(name)), file_type)
            self.assertIn(file_type, one_types.RAW_BRANDS[brand]["types"])
            self.assertIn(file_type, one_types.FILE_TYPE_ORDER)
            self.assertEqual(one_types.get_extensions_for_types([file_type]), {extension})
        self.assertEqual(one_types.get_file_type_for_path(Path("a.jpg")), "jpg")
        self.assertEqual(one_types.get_file_type_for_path(Path("a.txt")), "others")

    def test_existing_type_keys_and_labels_are_unchanged(self) -> None:
        self.assertEqual(one_types.get_file_type_label("cr3"), "Canon RAW (.CR3)")
        self.assertEqual(one_types.get_file_type_label("arw"), "Sony RAW (.ARW)")
        self.assertEqual(one_types.get_file_type_label("nrw"), "Nikon RAW (.NRW)")
        self.assertEqual(
            [t for t in one_types.FILE_TYPE_ORDER if t != "crw"],
            ["jpg", "cr3", "cr2", "arw", "srf", "sr2", "nef", "nrw"],
        )
        self.assertEqual(
            one_types.get_visible_file_types({"canon": True}), ["jpg", "cr3", "cr2", "crw"]
        )

    def test_helpers(self) -> None:
        self.assertEqual(raw_format_for("x/DSC1.ARW").brand, "sony")
        self.assertIsNone(raw_format_for("x/DSC1.JPG"))
        self.assertEqual(extensions_for_brand("nikon"), [".nef", ".nrw"])
        self.assertTrue(im_file_types.is_supported_image(Path("a.CRW")))
        self.assertEqual(im_file_types.media_type_for_path(Path("a.SRF")), "raw")


class SidecarNamingTests(unittest.TestCase):
    def test_raw_sidecar_is_stem_xmp_for_every_extension(self) -> None:
        for extension in sorted(EXPECTED):
            for suffix in (extension, extension.upper()):
                self.assertEqual(sidecar_path_for(Path(f"a/IMG_1{suffix}")), Path("a/IMG_1.xmp"))
        self.assertEqual(sidecar_path_for(Path("IMG_1.JPG")), Path("IMG_1.JPG.xmp"))


class SelectorMatchingTests(unittest.TestCase):
    def test_each_extension_matches_its_jpg(self) -> None:
        for extension in sorted(EXPECTED):
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / f"DSC01234{extension.upper()}").write_bytes(b"x")
                index = AutoSelectorService._index_cr3_files(root, False)
                raw, status, _c, _k = AutoSelectorService._match_details(index, "DSC01234")
                self.assertEqual(status, "matched")
                self.assertEqual(raw.suffix.lower(), extension)


class FakeExifTool:
    """Stands in for exiftool.exe: answers the size probe and -b extractions."""

    def __init__(self, tags: dict[str, bytes], orientation: int = 1, probe_ok: bool = True):
        self.tags = tags
        self.orientation = orientation
        self.probe_ok = probe_ok
        self.extracted: list[str] = []

    def __call__(self, command, **kwargs):
        if "-j" in command:
            if not self.probe_ok:
                return subprocess.CompletedProcess(command, 1, b"", b"boom")
            row = {"SourceFile": command[-1], "Orientation": self.orientation}
            for tag, data in self.tags.items():
                row[tag] = f"(Binary data {len(data)} bytes, use -b option to extract)"
            return subprocess.CompletedProcess(command, 0, json.dumps([row]).encode(), b"")
        tag = next(arg for arg in command if arg.startswith("-") and arg not in ("-b",))[1:]
        self.extracted.append(tag)
        return subprocess.CompletedProcess(command, 0, self.tags.get(tag, b""), b"")


class PreviewFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        reader = mock.Mock(exiftool_path=Path("exiftool.exe"))
        self.cache = CacheManager(self.root / "cache", reader)
        self.raw = self.root / "IMG_0001.CR3"
        self.raw.write_bytes(b"raw")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def proxy(self, fake: FakeExifTool) -> Image.Image:
        with mock.patch.object(cache_module.subprocess, "run", fake):
            path = self.cache.ensure_raw_proxy(self.raw)
        self.assertIsNotNone(path)
        return Image.open(path)

    def test_largest_embedded_jpeg_wins(self) -> None:
        small, large = jpeg_bytes((16, 8)), jpeg_bytes((300, 200))
        fake = FakeExifTool({"PreviewImage": small, "JpgFromRaw": large, "ThumbnailImage": jpeg_bytes((8, 4))})
        with self.proxy(fake) as image:
            self.assertEqual(image.size, (300, 200))
        self.assertEqual(fake.extracted, ["JpgFromRaw"])

    def test_only_a_thumbnail_is_still_used(self) -> None:
        fake = FakeExifTool({"ThumbnailImage": jpeg_bytes((160, 120))})
        with self.proxy(fake) as image:
            self.assertEqual(image.size, (160, 120))

    def test_unusable_largest_tag_falls_back_to_the_next(self) -> None:
        fake = FakeExifTool({"JpgFromRaw": b"\x00" * 5000, "PreviewImage": jpeg_bytes((120, 80))})
        with self.proxy(fake) as image:
            self.assertEqual(image.size, (120, 80))
        self.assertEqual(fake.extracted, ["JpgFromRaw", "PreviewImage"])

    def test_probe_failure_falls_back_to_fixed_order(self) -> None:
        fake = FakeExifTool({"PreviewImage": jpeg_bytes((120, 80))}, probe_ok=False)
        with self.proxy(fake) as image:
            self.assertEqual(image.size, (120, 80))
        self.assertEqual(fake.extracted, ["JpgFromRaw", "PreviewImage"])

    def test_no_preview_gives_placeholder_status(self) -> None:
        fake = FakeExifTool({})
        with mock.patch.object(cache_module.subprocess, "run", fake):
            proxy, thumbnail, status = self.cache.ensure_display_assets(self.raw)
        self.assertIsNone(proxy)
        self.assertEqual(status, "failed")
        self.assertTrue(thumbnail.exists())

    def test_raw_orientation_is_applied_to_preview_without_its_own(self) -> None:
        fake = FakeExifTool({"PreviewImage": jpeg_bytes((40, 20))}, orientation=6)
        with self.proxy(fake) as image:
            self.assertEqual(image.size, (20, 40))

    def test_preview_with_its_own_orientation_is_left_alone(self) -> None:
        data = jpeg_bytes((40, 20), orientation=6)
        fake = FakeExifTool({"PreviewImage": data}, orientation=6)
        with self.proxy(fake) as image:
            self.assertEqual(image.size, (40, 20))

    def test_all_eight_orientations_keep_pixel_count(self) -> None:
        for orientation in range(1, 9):
            out = cache_module._apply_raw_orientation(jpeg_bytes((40, 20)), orientation)
            with Image.open(io.BytesIO(out)) as image:
                expected = (20, 40) if orientation >= 5 else (40, 20)
                self.assertEqual(image.size, expected, orientation)


@unittest.skipUnless(os.environ.get("NDEX_RAW_SAMPLES"), "set NDEX_RAW_SAMPLES to a folder of RAW files")
class RealSampleTests(unittest.TestCase):
    def test_samples(self) -> None:
        folder = Path(os.environ["NDEX_RAW_SAMPLES"])
        files = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in RAW_EXTENSIONS]
        self.assertTrue(files, "no RAW files in NDEX_RAW_SAMPLES")
        extractor = MetadataExtractor()
        if not extractor.exiftool_path:
            self.skipTest("ExifTool not found")
        from dsb_image_manager.dsb_image_manager.services.metadata import MetadataReader

        reader = MetadataReader()
        with tempfile.TemporaryDirectory() as tmp:
            cache = CacheManager(Path(tmp), reader)
            for path in files:
                with self.subTest(file=path.name):
                    _when, source, fallback = extractor.get_capture_datetime(path)
                    self.assertEqual(source, "exiftool")
                    self.assertFalse(fallback)
                    self.assertNotEqual(one_types.get_file_type_for_path(path), "others")
                    proxy, thumbnail, status = cache.ensure_display_assets(path)
                    self.assertEqual(status, "embedded_preview")
                    with Image.open(proxy) as image:
                        self.assertGreaterEqual(max(image.size), 512)
                    self.assertTrue(thumbnail.exists())


if __name__ == "__main__":
    unittest.main()
