from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image, ImageCms

from ndex_frame.services.cache import CacheError, PreviewCache
from ndex_frame.services.importer import analyze_source


class PreviewCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.source_path = self.root / "master.jpg"
        self.cache = PreviewCache(self.root / "cache")
        self.write_source((3200, 1600), (80, 100, 120))
        self.source = analyze_source(self.source_path)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_source(self, size: tuple[int, int], color: tuple[int, int, int]) -> None:
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        Image.new("RGB", size, color).save(self.source_path, icc_profile=profile)

    def rewrite_source(self) -> None:
        time.sleep(0.01)
        self.write_source((3000, 1500), (140, 70, 20))
        self.source = analyze_source(self.source_path)

    def test_cache_reuses_unchanged_source(self) -> None:
        first = self.cache.get_or_create(self.source, 1600)
        second = self.cache.get_or_create(self.source, 1600)

        self.assertEqual(first, second)
        self.assertEqual(first.stat().st_mtime_ns, second.stat().st_mtime_ns)

    def test_cache_key_changes_after_source_modification(self) -> None:
        first = self.cache.get_or_create(self.source, 1600)
        self.rewrite_source()
        second = self.cache.get_or_create(self.source, 1600)

        self.assertNotEqual(first, second)

    def test_cache_writes_oriented_srgb_proxy_at_bounded_size_atomically(self) -> None:
        path = self.root / "rotated.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (300, 600), (80, 100, 120)).save(path, exif=exif)

        preview = self.cache.get_or_create(analyze_source(path), 200)

        self.assertTrue(preview.exists())
        self.assertEqual(list(preview.parent.glob("*.tmp")), [])
        with Image.open(preview) as image:
            self.assertEqual(image.size, (200, 100))
            self.assertTrue(image.info.get("icc_profile"))

    def test_cache_failure_is_exposed_as_service_error_for_preview_fallback(self) -> None:
        invalid_cache = PreviewCache(self.source_path)

        with self.assertRaises(CacheError):
            invalid_cache.get_or_create(self.source, 1600)


if __name__ == "__main__":
    unittest.main()
