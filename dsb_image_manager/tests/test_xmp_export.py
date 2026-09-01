from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from dsb_image_manager.dsb_image_manager.core.models import ImageRecord
from dsb_image_manager.dsb_image_manager.services.xmp_export import XmpExportService
from ndex_common.xmp import write_xmp_sidecar


def _make_record(file_path: Path, pick_status: str = "Unrated", rating: int = 0) -> ImageRecord:
    return ImageRecord(
        id=1,
        file_path=file_path,
        file_ext=file_path.suffix.lower(),
        base_name=file_path.stem,
        media_type="raw" if file_path.suffix.lower() == ".cr3" else "jpg",
        pair_group_id=file_path.stem.lower(),
        pair_status="raw_only",
        display_source=None,
        proxy_path=None,
        thumbnail_path=None,
        capture_datetime=None,
        file_modified_datetime=datetime(2026, 7, 3, 12, 0, 0),
        pick_status=pick_status,
        rating=rating,
    )


class XmpExportTests(unittest.TestCase):
    def test_export_writes_sidecar_for_picked_and_rated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "IMG_0001.CR3"
            raw.write_bytes(b"fake raw")

            summary = XmpExportService().export(
                [_make_record(raw, pick_status="Pick", rating=4)]
            )

            self.assertEqual(summary.written, 1)
            self.assertEqual(summary.errors, 0)
            xmp_path = root / "IMG_0001.xmp"
            self.assertTrue(xmp_path.exists())
            text = xmp_path.read_text(encoding="utf-8")
            self.assertIn('xmp:Rating="4"', text)
            self.assertIn('xmp:Label="NDEX Selected"', text)
            self.assertIn("NDEX Pick", text)
            self.assertTrue(raw.read_bytes() == b"fake raw")

    def test_export_skips_unrated_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "IMG_0002.CR3"
            raw.write_bytes(b"fake raw")

            summary = XmpExportService().export([_make_record(raw)])

            self.assertEqual(summary.written, 0)
            self.assertEqual(summary.skipped, 1)
            self.assertFalse((root / "IMG_0002.xmp").exists())

    def test_export_merges_into_existing_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "IMG_0003.CR3"
            raw.write_bytes(b"fake raw")
            write_xmp_sidecar(raw, rating=2, keywords=("Existing Keyword",))

            summary = XmpExportService().export(
                [_make_record(raw, pick_status="Maybe", rating=3)]
            )

            self.assertEqual(summary.written, 1)
            text = (root / "IMG_0003.xmp").read_text(encoding="utf-8")
            self.assertIn('xmp:Rating="3"', text)
            self.assertIn("Existing Keyword", text)
            self.assertIn("NDEX Maybe", text)
            ET.fromstring(text)

    def test_export_jpg_sidecar_does_not_collide_with_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "IMG_0004.CR3"
            jpg = root / "IMG_0004.JPG"
            raw.write_bytes(b"fake raw")
            jpg.write_bytes(b"fake jpg")

            summary = XmpExportService().export(
                [
                    _make_record(raw, pick_status="Pick", rating=5),
                    _make_record(jpg, pick_status="Maybe", rating=2),
                ]
            )

            self.assertEqual(summary.written, 2)
            self.assertTrue((root / "IMG_0004.xmp").exists())
            self.assertTrue((root / "IMG_0004.JPG.xmp").exists())
            self.assertIn('xmp:Rating="5"', (root / "IMG_0004.xmp").read_text(encoding="utf-8"))
            self.assertIn('xmp:Rating="2"', (root / "IMG_0004.JPG.xmp").read_text(encoding="utf-8"))

    def test_export_records_parse_and_value_errors_per_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "IMG_0005.CR3"
            raw.write_bytes(b"fake raw")
            record = _make_record(raw, pick_status="Pick", rating=4)

            with patch(
                "dsb_image_manager.dsb_image_manager.services.xmp_export.write_xmp_sidecar",
                side_effect=ValueError("invalid sidecar"),
            ):
                summary = XmpExportService().export([record])

            self.assertEqual(summary.written, 0)
            self.assertEqual(summary.errors, 1)
            self.assertEqual(len(summary.messages), 1)
            self.assertIn("IMG_0005.CR3", summary.messages[0])
            self.assertIn("invalid sidecar", summary.messages[0])


if __name__ == "__main__":
    unittest.main()
