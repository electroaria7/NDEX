from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ndex_frame.services.importer import analyze_source, discover_files


class ImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def make_image(self, name: str, size: tuple[int, int] = (30, 20)) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (20, 40, 60)).save(path)
        return path

    def test_discover_files_is_case_insensitive_and_sorted(self) -> None:
        self.make_image("B.PNG")
        self.make_image("a.jpg")
        (self.root / "notes.txt").write_text("ignore", encoding="utf-8")

        paths = discover_files([self.root])

        self.assertEqual([path.name for path in paths], ["a.jpg", "B.PNG"])

    def test_duplicate_selected_paths_are_returned_once(self) -> None:
        image = self.make_image("same.jpg")

        self.assertEqual(discover_files([image, image]), [image.resolve()])

    def test_discover_files_only_descends_when_recursive_is_requested(self) -> None:
        self.make_image("nested/child.tiff")

        self.assertEqual(discover_files([self.root]), [])
        self.assertEqual([path.name for path in discover_files([self.root], recursive=True)], ["child.tiff"])

    def test_analyze_source_reports_oriented_dimensions_and_missing_icc(self) -> None:
        path = self.root / "rotated.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (30, 20), (20, 40, 60)).save(path, exif=exif)

        source = analyze_source(path)

        self.assertEqual(source.path, path.resolve())
        self.assertEqual((source.oriented_width, source.oriented_height), (20, 30))
        self.assertFalse(source.has_icc)
        self.assertIn("색상 프로필 없음", source.warnings)


if __name__ == "__main__":
    unittest.main()
