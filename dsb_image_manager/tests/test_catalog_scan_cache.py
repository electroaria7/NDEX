from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from dsb_image_manager.dsb_image_manager.services.cache import CacheManager
from dsb_image_manager.dsb_image_manager.services.catalog import Catalog
from dsb_image_manager.dsb_image_manager.services.scanner import ImageScanner


def make_jpg(path: Path, color: str = "#4a90e2") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 60), color).save(path, "JPEG")


class ScannerCatalogCacheTests(unittest.TestCase):
    def test_pairing_is_per_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_jpg(root / "B" / "IMG_0001.JPG")
            (root / "A").mkdir()
            (root / "A" / "IMG_0001.CR3").write_bytes(b"fake raw")
            make_jpg(root / "C" / "IMG_0002.JPG")
            (root / "C" / "img_0002.cr3").write_bytes(b"fake raw")

            result = ImageScanner().scan(root)
            by_name = {(r.file_path.parent.name, r.file_ext): r for r in result.records}
            self.assertEqual(by_name[("B", "jpg")].pair_status, "jpg_only")
            self.assertEqual(by_name[("A", "cr3")].pair_status, "raw_only")
            self.assertEqual(by_name[("C", "jpg")].pair_status, "raw_jpg_pair")
            self.assertEqual(by_name[("C", "cr3")].pair_status, "raw_jpg_pair")
            self.assertEqual(result.pair_count, 1)
            self.assertNotEqual(by_name[("B", "jpg")].pair_group_id, by_name[("A", "cr3")].pair_group_id)

    def test_cache_key_changes_when_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "a.jpg"
            make_jpg(source, "#ff0000")
            cache = CacheManager(root / ".dsb_cache")
            first = cache.ensure_jpg_thumbnail(source)

            make_jpg(source, "#00ff00")
            stat = source.stat()
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
            second = cache.ensure_jpg_thumbnail(source)

            self.assertNotEqual(first, second)
            with Image.open(second) as image:
                self.assertGreater(image.convert("RGB").getpixel((210, 210))[1], 150)

    def test_truncated_cached_thumbnail_is_regenerated_without_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "a.jpg"
            make_jpg(source)
            cache = CacheManager(root / ".dsb_cache")
            thumb = cache.ensure_jpg_thumbnail(source)
            thumb.write_bytes(thumb.read_bytes()[:20])

            again = cache.ensure_jpg_thumbnail(source)
            self.assertEqual(again, thumb)
            with Image.open(again) as image:
                image.load()
            self.assertEqual(list((root / ".dsb_cache").rglob("*.tmp")), [])

    def test_rescan_keeps_backup_status_unless_file_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "a.jpg"
            make_jpg(photo)
            result = ImageScanner().scan(root)
            catalog = Catalog(result.catalog_path)
            catalog.update_backup_status(result.records[0].id, "backed_up")
            catalog.close()

            again = ImageScanner().scan(root)
            self.assertEqual(again.records[0].backup_status, "backed_up")

            stat = photo.stat()
            os.utime(photo, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
            changed = ImageScanner().scan(root)
            self.assertEqual(changed.records[0].backup_status, "not_backed_up")

    def test_rescan_removes_rows_for_deleted_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_jpg(root / "keep.jpg")
            make_jpg(root / "sub" / "gone.jpg")
            result = ImageScanner().scan(root)
            gone = next(r for r in result.records if r.file_path.name == "gone.jpg")
            catalog = Catalog(result.catalog_path)
            catalog.update_selection(gone.id, pick_status="Pick")
            catalog.close()

            (root / "sub" / "gone.jpg").unlink()
            again = ImageScanner().scan(root)
            self.assertEqual([r.file_path.name for r in again.records], ["keep.jpg"])
            catalog = Catalog(result.catalog_path)
            names = [r.file_path.name for r in catalog.list_images()]
            orphans = catalog.connection.execute("SELECT COUNT(*) FROM selection").fetchone()[0]
            catalog.close()
            self.assertEqual(names, ["keep.jpg"])
            self.assertEqual(orphans, 1)


if __name__ == "__main__":
    unittest.main()
