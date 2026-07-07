from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from dsb_image_manager.dsb_image_manager.services.backup import BackupService
from dsb_image_manager.dsb_image_manager.services.catalog import Catalog
from dsb_image_manager.dsb_image_manager.core.models import ExportOptions
from dsb_image_manager.dsb_image_manager.services.exporter import ExportService, render_export_stem
from dsb_image_manager.dsb_image_manager.services.metadata import metadata_from_exiftool_row
from dsb_image_manager.dsb_image_manager.services.scanner import ImageScanner


class ImageManagerServiceTests(unittest.TestCase):
    def test_scanner_detects_jpg_raw_pair_and_persists_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_jpg(root / "IMG_0001.JPG")
            (root / "IMG_0001.CR3").write_bytes(b"fake raw")

            result = ImageScanner().scan(root)
            self.assertEqual(result.total, 2)
            self.assertEqual(result.pair_count, 1)
            self.assertTrue((root / ".dsb_cache" / "catalog.sqlite").exists())

            catalog = Catalog(result.catalog_path)
            first = catalog.list_images(sort_key="file_name")[0]
            self.assertEqual(first.pair_status, "raw_jpg_pair")
            catalog.update_selection(first.id, pick_status="Pick", rating=5)
            updated = catalog.list_images(pick_filter="Pick")[0]
            catalog.close()

            self.assertEqual(updated.pick_status, "Pick")
            self.assertEqual(updated.rating, 5)

    def test_backup_uses_dsb_date_folder_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            destination = root / "backup"
            self._make_jpg(source / "IMG_0002.JPG")

            result = ImageScanner().scan(source)
            summary = BackupService().backup(result.records, destination)

            self.assertEqual(summary.copied, 1)
            copied = list(destination.rglob("IMG_0002.JPG"))
            self.assertEqual(len(copied), 1)
            self.assertIn("JPG", copied[0].parts)

    def test_export_copies_selected_images_with_renamed_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            destination = root / "export"
            self._make_jpg(source / "IMG_0003.JPG")
            self._make_jpg(source / "IMG_0004.JPG")

            result = ImageScanner().scan(source)
            options = ExportOptions(
                destination_dir=destination,
                rename_pattern="DSB_{index}_{name}_{rating}",
            )
            summary = ExportService().export(result.records, options)

            self.assertEqual(summary.exported, 2)
            exported_names = sorted(path.name for path in destination.iterdir())
            self.assertEqual(exported_names, ["DSB_001_IMG_0003_0.JPG", "DSB_002_IMG_0004_0.JPG"])

    def test_export_pattern_cannot_create_nested_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_jpg(root / "IMG_0005.JPG")

            record = ImageScanner().scan(root).records[0]
            stem = render_export_stem(record, "../unsafe/{name}\\nested", 1)

            self.assertNotIn("/", stem)
            self.assertNotIn("\\", stem)
            self.assertNotIn("..", stem)

    def test_cr3_exiftool_fallback_tags_are_mapped(self) -> None:
        metadata = metadata_from_exiftool_row(
            {
                "SourceFile": "IMG_1001.CR3",
                "SubSecDateTimeOriginal": "2026-05-08 14:15:16.42-05:00",
                "CameraModelName": "Canon EOS R5",
                "LensID": "RF24-70mm F2.8 L IS USM",
                "ShutterSpeed": "1/250",
                "Aperture": "f/2.8",
                "ISOSpeedRatings": 400,
                "ImageSize": "8192x5464",
                "ColorRepresentation": "sRGB",
            }
        )

        self.assertEqual(metadata.capture_datetime.strftime("%Y-%m-%d %H:%M:%S"), "2026-05-08 14:15:16")
        self.assertEqual(metadata.camera_model, "Canon EOS R5")
        self.assertEqual(metadata.lens_model, "RF24-70mm F2.8 L IS USM")
        self.assertEqual(metadata.exposure_time, "1/250")
        self.assertEqual(metadata.aperture, "2.8")
        self.assertEqual(metadata.iso, "400")
        self.assertEqual(metadata.width, 8192)
        self.assertEqual(metadata.height, 5464)
        self.assertEqual(metadata.color_space, "sRGB")
        self.assertTrue(metadata.has_exif)

    @staticmethod
    def _make_jpg(path: Path) -> None:
        image = Image.new("RGB", (80, 60), "#4a90e2")
        image.save(path, "JPEG")


if __name__ == "__main__":
    unittest.main()
