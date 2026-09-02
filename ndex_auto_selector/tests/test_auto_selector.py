from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ndex_auto_selector.ndex_auto_selector.services.selector import AutoSelectorService


class AutoSelectorServiceTests(unittest.TestCase):
    def test_analyze_matches_selected_jpg_to_cr3_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_source = root / "raw"
            selected = root / "selected"
            raw_source.mkdir()
            selected.mkdir()
            (raw_source / "IMG_0001.CR3").write_text("raw", encoding="utf-8")
            (raw_source / "IMG_0002.CR3").write_text("raw", encoding="utf-8")
            (selected / "img_0001.jpg").write_text("jpg", encoding="utf-8")
            (selected / "IMG_9999.JPG").write_text("jpg", encoding="utf-8")

            summary = AutoSelectorService().analyze(raw_source, selected)

            self.assertEqual(summary.selected_count, 2)
            self.assertEqual(summary.matched_count, 1)
            self.assertEqual(summary.missing_count, 1)
            self.assertEqual(summary.matches[0].raw_path, raw_source / "IMG_0001.CR3")

    def test_copy_matches_renames_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_source = root / "raw"
            selected = root / "selected"
            work = root / "work"
            raw_source.mkdir()
            selected.mkdir()
            work.mkdir()
            (raw_source / "IMG_0001.CR3").write_text("new raw", encoding="utf-8")
            (selected / "IMG_0001.JPG").write_text("jpg", encoding="utf-8")
            (work / "IMG_0001.CR3").write_text("existing", encoding="utf-8")

            service = AutoSelectorService()
            summary = service.analyze(raw_source, selected)
            result = service.copy_matches(summary.matches, work, "rename")

            self.assertEqual(result.copied, 1)
            self.assertTrue((work / "IMG_0001_001.CR3").exists())

    def test_analyze_matches_embedded_img_number_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_source = root / "raw"
            selected = root / "selected"
            raw_source.mkdir()
            selected.mkdir()
            (raw_source / "IMG_0123.CR3").write_text("raw", encoding="utf-8")
            (selected / "client_pick_IMG_0123_edit.JPG").write_text("jpg", encoding="utf-8")

            summary = AutoSelectorService().analyze(raw_source, selected)

            self.assertEqual(summary.matched_count, 1)
            self.assertEqual(summary.matches[0].raw_path, raw_source / "IMG_0123.CR3")

    def test_copy_matches_writes_selected_xmp_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_source = root / "raw"
            selected = root / "selected"
            work = root / "work"
            raw_source.mkdir()
            selected.mkdir()
            work.mkdir()
            (raw_source / "IMG_0001.CR3").write_text("raw", encoding="utf-8")
            (selected / "IMG_0001.JPG").write_text("jpg", encoding="utf-8")

            service = AutoSelectorService()
            summary = service.analyze(raw_source, selected)
            result = service.copy_matches(summary.matches, work, "rename", write_xmp=True)

            xmp_path = work / "IMG_0001.xmp"
            self.assertEqual(result.xmp_written, 1)
            self.assertTrue(xmp_path.exists())
            xmp_text = xmp_path.read_text(encoding="utf-8")
            self.assertIn('xmp:Rating="5"', xmp_text)
            self.assertIn('xmp:Label="NDEX Selected"', xmp_text)
            self.assertIn("NDEX Selected", xmp_text)

    def test_analyze_marks_ambiguous_when_duplicate_raw_tokens_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_source = root / "raw"
            selected = root / "selected"
            card_a = raw_source / "card_a"
            card_b = raw_source / "card_b"
            for folder in (card_a, card_b, selected):
                folder.mkdir(parents=True)
            (card_a / "IMG_0001.CR3").write_text("raw-a", encoding="utf-8")
            (card_b / "IMG_0001.CR3").write_text("raw-b", encoding="utf-8")
            (selected / "IMG_0001.JPG").write_text("jpg", encoding="utf-8")

            summary = AutoSelectorService().analyze(raw_source, selected, recursive=True)

            self.assertEqual(summary.selected_count, 1)
            self.assertEqual(summary.matched_count, 0)
            self.assertEqual(summary.ambiguous_count, 1)
            self.assertEqual(summary.matches[0].status, "ambiguous")
            self.assertIsNone(summary.matches[0].raw_path)

            result = AutoSelectorService().copy_matches(summary.matches, root / "work")
            self.assertEqual(result.ambiguous, 1)
            self.assertEqual(result.copied, 0)
            self.assertFalse(list((root / "work").glob("*.CR3")))

class RetrySelectionTests(unittest.TestCase):
    """A retry narrows a fresh analysis down to the JPGs that went wrong."""

    def _folders(self, root: Path) -> tuple[Path, Path]:
        raw_source = root / "raw"
        selected = root / "selected"
        raw_source.mkdir()
        selected.mkdir()
        return raw_source, selected

    def test_matches_for_keeps_only_the_named_jpgs_in_that_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_source, selected = self._folders(root)
            for index in (1, 2, 3):
                (raw_source / f"IMG_000{index}.CR3").write_text("raw", encoding="utf-8")
                (selected / f"IMG_000{index}.JPG").write_text("jpg", encoding="utf-8")

            service = AutoSelectorService()
            summary = service.analyze(raw_source, selected)
            wanted = [selected / "IMG_0003.JPG", selected / "IMG_0001.JPG"]
            found = service.matches_for(summary.matches, wanted)

        self.assertEqual([match.jpg_path for match in found], wanted)

    def test_a_jpg_that_is_no_longer_in_the_folder_is_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_source, selected = self._folders(root)
            (raw_source / "IMG_0001.CR3").write_text("raw", encoding="utf-8")
            (selected / "IMG_0001.JPG").write_text("jpg", encoding="utf-8")

            service = AutoSelectorService()
            summary = service.analyze(raw_source, selected)
            found = service.matches_for(
                summary.matches, [selected / "IMG_0001.JPG", selected / "IMG_0404.JPG"]
            )

        self.assertEqual([match.jpg_path for match in found], [selected / "IMG_0001.JPG"])

    def test_a_raw_added_since_the_failed_run_now_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_source, selected = self._folders(root)
            jpg = selected / "IMG_0001.JPG"
            jpg.write_text("jpg", encoding="utf-8")

            service = AutoSelectorService()
            before = service.analyze(raw_source, selected)
            self.assertEqual(before.matches[0].status, "missing")

            # The point of a retry: the photographer went and found the RAW.
            (raw_source / "IMG_0001.CR3").write_text("raw", encoding="utf-8")
            after = service.matches_for(service.analyze(raw_source, selected).matches, [jpg])
            result = service.copy_matches(after, root / "work")

        self.assertEqual(result.copied, 1)
        self.assertEqual(result.missing, 0)



if __name__ == "__main__":
    unittest.main()
