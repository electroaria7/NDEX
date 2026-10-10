from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dsb_image_manager.dsb_image_manager.services import metadata as image_manager_metadata
from src import metadata as one_metadata
from src.metadata import MetadataExtractor

KOREAN_NAME = "한글폴더"


class _Completed:
    def __init__(self, stdout: bytes, returncode: int = 0, stderr: bytes = b""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _fake_exiftool(rows_for, captured, stdout_override=None):
    """subprocess.run stand-in that reads the argfile the way ExifTool would."""

    def run(command, **kwargs):
        captured["kwargs"] = kwargs
        captured["command"] = command
        argfile = Path(command[command.index("-@") + 1])
        captured["argfile"] = argfile
        names = argfile.read_text(encoding="utf-8").splitlines()
        captured["names"] = names
        if stdout_override is not None:
            return _Completed(stdout_override)
        return _Completed(json.dumps(rows_for(names), ensure_ascii=False).encode("utf-8"))

    return run


class OneExifToolTests(unittest.TestCase):
    def _extractor(self) -> MetadataExtractor:
        extractor = MetadataExtractor.__new__(MetadataExtractor)
        extractor.exiftool_path = "exiftool"
        extractor.batch_size = 50
        extractor.timeout_seconds = 5
        return extractor

    def test_non_ascii_paths_use_utf8_argfile_and_match_forward_slash_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / KOREAN_NAME / "IMG_0001.CR3"
            photo.parent.mkdir()
            photo.write_text("raw", encoding="utf-8")
            captured: dict = {}

            def rows(names):
                return [
                    {"SourceFile": name.replace("\\", "/"), "DateTimeOriginal": "2024:03:05 10:20:30"}
                    for name in names
                ]

            with patch.object(one_metadata.subprocess, "run", _fake_exiftool(rows, captured)):
                dates, error = self._extractor()._from_exiftool_chunk([photo])

            self.assertIsNone(error)
            self.assertEqual(list(dates), [photo])
            self.assertEqual(captured["names"], [str(photo)])
            self.assertIn("filename=utf8", captured["command"])
            self.assertFalse(captured["kwargs"].get("text"))
            self.assertNotIn(str(photo), captured["command"])
            self.assertFalse(captured["argfile"].exists())

    def test_undecodable_output_is_not_fatal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / "IMG_0001.CR3"
            photo.write_text("raw", encoding="utf-8")
            row = b'[{"SourceFile": "x\xff", "DateTimeOriginal": "2024:03:05 10:20:30"}]'
            captured: dict = {}
            with patch.object(
                one_metadata.subprocess, "run", _fake_exiftool(None, captured, row)
            ):
                dates, error = self._extractor()._from_exiftool_chunk([photo])

        self.assertIsNone(error)
        self.assertEqual(len(dates), 1)

    def test_vanished_file_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "gone.CR3"
            extractor = self._extractor()
            extractor.exiftool_path = None
            results = extractor.get_capture_datetimes([missing])

        self.assertEqual(results, {})


class ImageManagerExifToolTests(unittest.TestCase):
    def _reader(self):
        reader = image_manager_metadata.MetadataReader.__new__(
            image_manager_metadata.MetadataReader
        )
        reader.exiftool_path = Path("exiftool")
        return reader

    def test_non_ascii_paths_use_utf8_argfile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            photo = Path(temp_dir) / KOREAN_NAME / "IMG_0001.JPG"
            photo.parent.mkdir()
            photo.write_text("jpg", encoding="utf-8")
            captured: dict = {}

            def rows(names):
                return [{"SourceFile": name.replace("\\", "/"), "Model": "Cam"} for name in names]

            with patch.object(
                image_manager_metadata.subprocess, "run", _fake_exiftool(rows, captured)
            ):
                results = self._reader()._read_exiftool_chunk([photo])

            self.assertEqual(list(results), [photo])
            self.assertEqual(results[photo].camera_model, "Cam")
            self.assertIn("filename=utf8", captured["command"])
            self.assertFalse(captured["argfile"].exists())

    def test_undecodable_output_is_not_fatal(self):
        with patch.object(
            image_manager_metadata.subprocess,
            "run",
            lambda *a, **k: _Completed(b"\xff\xfe not json"),
        ):
            self.assertEqual(self._reader()._read_exiftool_chunk([Path("a.jpg")]), {})


if __name__ == "__main__":
    unittest.main()
