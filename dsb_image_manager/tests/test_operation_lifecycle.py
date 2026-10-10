from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image

from dsb_image_manager.dsb_image_manager.core.models import ExportOptions, ImageRecord
from dsb_image_manager.dsb_image_manager.services.backup import BackupService
from dsb_image_manager.dsb_image_manager.services.catalog import Catalog
from dsb_image_manager.dsb_image_manager.services.exporter import ExportService
from dsb_image_manager.dsb_image_manager.services.scanner import ImageScanner, ScanCancelled
from dsb_image_manager.dsb_image_manager.services.xmp_export import XmpExportService


def make_record(path: Path, identifier: int) -> ImageRecord:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 12), "navy").save(path, "JPEG")
    return ImageRecord(identifier, path, "jpg", path.stem, "jpg", path.stem, "jpg_only",
                       path, None, None, None, datetime(2026, 10, 10), pick_status="Pick", rating=4)


class FastMetadata:
    exiftool_path = None

    def read_batch(self, paths):
        return {}


class OperationLifecycleTests(unittest.TestCase):
    def test_cancel_finishes_one_file_and_records_every_unprocessed_source(self):
        for kind in ("backup", "export", "xmp"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                records = [make_record(root / "source" / f"{i}.jpg", i) for i in range(3)]
                original = {r.file_path: r.file_path.read_bytes() for r in records}
                cancel = threading.Event()
                progress = []

                def report(index, total, path):
                    progress.append((index, total, path))
                    if index == 1:
                        cancel.set()

                if kind == "backup":
                    result = BackupService().backup(records, root / "out", cancel_event=cancel, progress_callback=report)
                elif kind == "export":
                    result = ExportService().export(records, ExportOptions(root / "out", "{name}"),
                                                    cancel_event=cancel, progress_callback=report)
                else:
                    result = XmpExportService().export(records, cancel_event=cancel, progress_callback=report)
                self.assertTrue(result.cancelled)
                self.assertEqual(result.errors, 2)
                self.assertEqual(len(result.items), 3)
                self.assertEqual([item["detail"] for item in result.items if item["status"] == "failed"],
                                 ["not run: cancelled"] * 2)
                first = result.items[0]
                self.assertTrue(Path(first["destination"]).is_file())
                self.assertEqual(progress[-1][:2], (1, 3))
                for path, content in original.items():
                    self.assertEqual(path.read_bytes(), content)
                self.assertEqual(list(root.rglob("*.ndex_tmp")), [])

    def test_scan_cancel_keeps_catalog_and_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_record(root / "a.jpg", 1)
            initial = ImageScanner(FastMetadata()).scan(root)
            catalog = Catalog(initial.catalog_path)
            catalog.update_selection(initial.records[0].id, pick_status="Pick", rating=5)
            catalog.close()
            make_record(root / "b.jpg", 2)
            cancel = threading.Event()

            class CancellingMetadata(FastMetadata):
                def read_batch(self, paths):
                    cancel.set()
                    return {}

            with self.assertRaises(ScanCancelled):
                ImageScanner(CancellingMetadata()).scan(root, cancel_event=cancel)
            catalog = Catalog(initial.catalog_path)
            records = catalog.list_images()
            catalog.close()
            self.assertEqual([(r.display_name, r.pick_status, r.rating) for r in records], [("a.jpg", "Pick", 5)])

    def test_scanner_prunes_cache_before_traversing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_record(root / "real.jpg", 1)
            make_record(root / ".DSB_CACHE" / "nested" / "cached.jpg", 2)
            traversed = []
            original = os.scandir

            def scandir(path):
                traversed.append(Path(path))
                return original(path)

            with patch("os.scandir", side_effect=scandir):
                paths = ImageScanner._find_images(root, True)
            self.assertEqual([path.name for path in paths], ["real.jpg"])
            self.assertFalse(any(".dsb_cache" in str(path).lower() for path in traversed))

    def test_bulk_selection_uses_one_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = Catalog(root / "catalog.sqlite")
            records = [make_record(root / f"{i}.jpg", i) for i in range(5)]
            catalog.upsert_images(records)
            statements = []
            catalog.connection.set_trace_callback(statements.append)
            catalog.update_selections([r.id for r in records], pick_status="Maybe", rating=2)
            self.assertEqual(sum(statement == "COMMIT" for statement in statements), 1)
            self.assertTrue(all(r.pick_status == "Maybe" and r.rating == 2 for r in catalog.list_images()))
            catalog.close()


if __name__ == "__main__":
    unittest.main()
