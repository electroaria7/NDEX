from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from dsb_image_manager.dsb_image_manager.core.models import ImageRecord
from dsb_image_manager.dsb_image_manager.services.xmp_export import XmpExportService
from ndex_common import session, settings as shared_settings
from ndex_common.workflow import record_export, record_select_handoff
from ndex_common.xmp import XMP_NS, write_xmp_sidecar
from ndex_launcher.state import gather_workflow_state
from tests.test_workflow import patch_roots

XMP_HEAD = (
    '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf='
    '"http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
    'xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"'
)


def _record(path: Path, pick_status: str = "Unrated", rating: int = 0) -> ImageRecord:
    return ImageRecord(
        id=1,
        file_path=path,
        file_ext=path.suffix.lower(),
        base_name=path.stem,
        media_type="raw" if path.suffix.lower() == ".cr3" else "jpg",
        pair_group_id=path.stem.lower(),
        pair_status="raw_only",
        display_source=None,
        proxy_path=None,
        thumbnail_path=None,
        capture_datetime=None,
        file_modified_datetime=datetime(2026, 7, 3, 12, 0, 0),
        pick_status=pick_status,
        rating=rating,
    )


class XmpWriterTests(unittest.TestCase):
    def test_jpg_sidecar_does_not_inherit_raw_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_xmp_sidecar(root / "IMG_1.CR3", rating=5, label="Red", keywords=("RawOnly",))
            jpg_xmp = write_xmp_sidecar(root / "IMG_1.JPG", rating=2)
            text = jpg_xmp.read_text(encoding="utf-8")
            self.assertNotIn("RawOnly", text)
            self.assertNotIn("Red", text)
            self.assertIn('xmp:Rating="2"', text)

    def test_child_element_rating_and_label_are_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "IMG_2.CR3"
            (root / "IMG_2.xmp").write_text(
                XMP_HEAD + "><xmp:Rating>3</xmp:Rating><xmp:Label>Blue</xmp:Label>"
                "</rdf:Description></rdf:RDF></x:xmpmeta>",
                encoding="utf-8",
            )
            path = write_xmp_sidecar(raw, rating=5, label="NDEX Selected")
            description = ET.parse(path).getroot().find(
                ".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"
            )
            self.assertEqual(description.findall(f"{{{XMP_NS}}}Rating"), [])
            self.assertEqual(description.findall(f"{{{XMP_NS}}}Label"), [])
            self.assertEqual(description.get(f"{{{XMP_NS}}}Rating"), "5")
            self.assertEqual(description.get(f"{{{XMP_NS}}}Label"), "NDEX Selected")

    def test_temp_name_is_unique_per_write(self) -> None:
        from ndex_common import xmp

        names = []
        real_replace = xmp.os.replace

        def spy(src, dst):
            names.append(Path(src).name)
            return real_replace(src, dst)

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(xmp.os, "replace", side_effect=spy):
                write_xmp_sidecar(Path(tmp) / "a.CR3", rating=1)
                write_xmp_sidecar(Path(tmp) / "a.CR3", rating=2)
        self.assertEqual(len(set(names)), 2)

    def test_remove_keywords_and_conditional_label_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "IMG_3.CR3"
            write_xmp_sidecar(raw, label="Mine", keywords=("Keep", "NDEX Pick"))
            path = write_xmp_sidecar(raw, remove_keywords=("NDEX Pick",), clear_label_if=("NDEX Selected",))
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("NDEX Pick", text)
            self.assertIn("Keep", text)
            self.assertIn('xmp:Label="Mine"', text)


class XmpExportStaleStateTests(unittest.TestCase):
    def test_pick_to_reject_and_back_to_unrated_clears_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "IMG_4.CR3"
            raw.write_bytes(b"raw")
            service = XmpExportService()
            service.export([_record(raw, "Pick", 4)])
            service.export([_record(raw, "Reject", 1)])
            text = (root / "IMG_4.xmp").read_text(encoding="utf-8")
            self.assertNotIn("NDEX Selected", text)
            self.assertNotIn("NDEX Pick", text)
            self.assertIn("NDEX Reject", text)

            summary = service.export([_record(raw)])
            text = (root / "IMG_4.xmp").read_text(encoding="utf-8")
            self.assertEqual(summary.written, 1)
            self.assertNotIn("NDEX", text)

    def test_unrated_without_sidecar_creates_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "IMG_5.CR3"
            raw.write_bytes(b"raw")
            summary = XmpExportService().export([_record(raw)])
            self.assertEqual(summary.skipped, 1)
            self.assertFalse((Path(tmp) / "IMG_5.xmp").exists())


class SettingsRobustnessTests(unittest.TestCase):
    def test_bom_settings_file_is_read_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"frame": {"a": 1}}).encode())
            with patch.object(shared_settings, "settings_path", return_value=path):
                shared_settings.update_section("launcher", {"b": 2})
                stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["frame"], {"a": 1})
            self.assertEqual(stored["launcher"], {"b": 2})

    def test_invalid_utf8_does_not_raise_and_is_not_destroyed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_bytes(b"\xff\xfe\x00bad")
            with patch.object(shared_settings, "settings_path", return_value=path):
                self.assertIsInstance(shared_settings.load_all(), dict)
                shared_settings.update_section("launcher", {"b": 2})
            corrupt = list(Path(tmp).glob("settings.json.corrupt-*"))
            self.assertEqual(len(corrupt), 1)
            self.assertEqual(corrupt[0].read_bytes(), b"\xff\xfe\x00bad")
            bak = path.with_name("settings.json.bak")
            self.assertFalse(bak.exists() and bak.read_bytes() == b"\xff\xfe\x00bad")

    def test_corrupt_file_restores_from_good_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.with_name("settings.json.bak").write_text(
                json.dumps({"frame": {"a": 1}}), encoding="utf-8"
            )
            path.write_text("{ not json", encoding="utf-8")
            with patch.object(shared_settings, "settings_path", return_value=path):
                shared_settings.update_section("launcher", {"b": 2})
                stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["frame"], {"a": 1})
            self.assertEqual(stored["launcher"], {"b": 2})


class StaleHandoffTests(unittest.TestCase):
    def test_normal_frame_export_clears_old_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root / "photos"
            photos.mkdir()
            pick = photos / "pick.jpg"
            pick.write_bytes(b"jpg")
            other = root / "other"
            other.mkdir()
            out = root / "out"
            out.mkdir()
            with ExitStack() as stack:
                for p in patch_roots(root):
                    stack.enter_context(p)
                self.assertIsNotNone(record_select_handoff(photos, [pick]))
                before = session.load_session("frame")
                self.assertTrue(before["context"].get("handoff"))

                record_export(other, out, type("R", (), {"items": [], "exported": 0})())
                after = session.load_session("frame")
                self.assertNotIn("handoff", after["context"])
                args = session.launch_args(after)
                self.assertNotIn("--handoff", args)
                self.assertIn(str(other), args)

    def test_image_manager_card_never_reports_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root / "photos"
            photos.mkdir()
            pick = photos / "pick.jpg"
            pick.write_bytes(b"jpg")
            with ExitStack() as stack:
                for p in patch_roots(root):
                    stack.enter_context(p)
                record_select_handoff(photos, [pick])
                steps = {step.key: step for step in gather_workflow_state()}
            self.assertFalse(steps["image_manager"].handoff_ready)
            self.assertTrue(steps["frame"].handoff_ready)


if __name__ == "__main__":
    unittest.main()
