from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ndex_auto_selector.ndex_auto_selector.services.selector import AutoSelectorService
from ndex_common.rating import read_jpg_rating
from ndex_common.xmp import write_xmp_sidecar


class RatingFromJpgTests(unittest.TestCase):
    def test_read_rating_from_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jpg = root / "IMG_0001.JPG"
            jpg.write_bytes(b"fake jpg")
            write_xmp_sidecar(jpg, rating=3)

            self.assertEqual(read_jpg_rating(jpg), 3)

    def test_read_rating_from_embedded_xmp_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jpg = root / "IMG_0002.JPG"
            jpg.write_bytes(b'\xff\xd8\xff\xe1 http://ns.adobe.com/xap/1.0/ xmp:Rating="4" tail')

            self.assertEqual(read_jpg_rating(jpg), 4)

    def test_read_rating_returns_none_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jpg = root / "IMG_0003.JPG"
            jpg.write_bytes(b"fake jpg no rating")

            self.assertIsNone(read_jpg_rating(jpg))

    def test_copy_matches_uses_jpg_rating_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            jpg_dir = root / "selects"
            work = root / "work"
            raw_dir.mkdir()
            jpg_dir.mkdir()

            (raw_dir / "IMG_0010.CR3").write_bytes(b"raw")
            jpg = jpg_dir / "IMG_0010.JPG"
            jpg.write_bytes(b"jpg")
            write_xmp_sidecar(jpg, rating=2)

            service = AutoSelectorService()
            summary = service.analyze(raw_dir, jpg_dir)
            result = service.copy_matches(
                summary.matches,
                work,
                "rename",
                write_xmp=True,
                xmp_rating=5,
                rating_from_jpg=True,
            )

            self.assertEqual(result.copied, 1)
            text = (work / "IMG_0010.xmp").read_text(encoding="utf-8")
            self.assertIn('xmp:Rating="2"', text)

    def test_copy_matches_falls_back_to_default_rating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            jpg_dir = root / "selects"
            work = root / "work"
            raw_dir.mkdir()
            jpg_dir.mkdir()

            (raw_dir / "IMG_0011.CR3").write_bytes(b"raw")
            (jpg_dir / "IMG_0011.JPG").write_bytes(b"jpg without rating")

            service = AutoSelectorService()
            summary = service.analyze(raw_dir, jpg_dir)
            result = service.copy_matches(
                summary.matches,
                work,
                "rename",
                write_xmp=True,
                xmp_rating=5,
                rating_from_jpg=True,
            )

            self.assertEqual(result.copied, 1)
            text = (work / "IMG_0011.xmp").read_text(encoding="utf-8")
            self.assertIn('xmp:Rating="5"', text)


class MultiVendorMatchTests(unittest.TestCase):
    def _analyze(self, raw_name: str, jpg_name: str):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            jpg_dir = root / "selects"
            raw_dir.mkdir()
            jpg_dir.mkdir()
            (raw_dir / raw_name).write_bytes(b"raw")
            (jpg_dir / jpg_name).write_bytes(b"jpg")
            summary = AutoSelectorService().analyze(raw_dir, jpg_dir)
            return summary.matches[0]

    def test_sony_arw_token_match(self) -> None:
        match = self._analyze("DSC01234.ARW", "wedding_DSC01234_pick.JPG")
        self.assertIsNotNone(match.raw_path)
        self.assertEqual(match.raw_path.name, "DSC01234.ARW")

    def test_nikon_nef_underscore_prefix_match(self) -> None:
        match = self._analyze("_DSC0042.NEF", "blog__DSC0042_final.jpg")
        self.assertIsNotNone(match.raw_path)
        self.assertEqual(match.raw_path.name, "_DSC0042.NEF")

    def test_nikon_nef_dsc_underscore_match(self) -> None:
        match = self._analyze("DSC_0007.nef", "album_DSC_0007.JPEG")
        self.assertIsNotNone(match.raw_path)
        self.assertEqual(match.raw_path.name, "DSC_0007.nef")

    def test_canon_cr2_still_matches(self) -> None:
        match = self._analyze("IMG_9999.CR2", "pick_IMG_9999_edit.jpg")
        self.assertIsNotNone(match.raw_path)
        self.assertEqual(match.raw_path.name, "IMG_9999.CR2")

    def test_unrelated_names_do_not_match(self) -> None:
        match = self._analyze("DSC01234.ARW", "random_photo.jpg")
        self.assertIsNone(match.raw_path)


if __name__ == "__main__":
    unittest.main()
