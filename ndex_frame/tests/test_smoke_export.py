from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageCms

from ndex_frame.main import build_parser, main
from ndex_frame.services.export_job import ExportItemResult, ExportResult


COPYRIGHT_TAG = 33432
GPS_TAG = 34853


class SmokeExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "master.jpg"
        self.output_dir = self.root / "out"
        self.output_dir.mkdir()
        Image.new("RGB", (40, 60), (20, 40, 60)).save(self.source)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_parser_accepts_hidden_smoke_export_paths(self) -> None:
        args = build_parser().parse_args(
            ["--smoke-export", str(self.source), str(self.output_dir)]
        )
        self.assertEqual(args.smoke_export, [self.source, self.output_dir])
        self.assertNotIn("smoke-export", build_parser().format_help())

    def test_smoke_export_does_not_construct_qapplication(self) -> None:
        destination = self.output_dir / "master.jpg"
        fake_result = ExportResult(
            exported=1,
            skipped=0,
            failed=0,
            cancelled=False,
            items=(ExportItemResult(self.source, destination, "exported"),),
        )
        stdout = io.StringIO()
        with (
            patch("ndex_frame.main.QApplication") as qapplication,
            patch("ndex_frame.main.run_export", create=True, return_value=fake_result) as run_export,
            patch("sys.stdout", stdout),
        ):
            code = main(["--smoke-export", str(self.source), str(self.output_dir)])

        qapplication.assert_not_called()
        run_export.assert_called_once()
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(payload["exported"], 1)
        self.assertEqual(payload["items"][0]["destination"], str(destination))

    def test_smoke_export_exits_nonzero_unless_one_file_exported(self) -> None:
        fake_result = ExportResult(
            exported=0,
            skipped=0,
            failed=1,
            cancelled=False,
            items=(ExportItemResult(self.source, self.output_dir / "master.jpg", "failed", "boom"),),
        )
        with (
            patch("ndex_frame.main.QApplication") as qapplication,
            patch("ndex_frame.main.run_export", create=True, return_value=fake_result),
            patch("sys.stdout", io.StringIO()),
        ):
            code = main(["--smoke-export", str(self.source), str(self.output_dir)])

        qapplication.assert_not_called()
        self.assertEqual(code, 1)


class SmokeExportIntegrationTests(unittest.TestCase):
    def test_smoke_export_produces_framed_jpeg_without_starting_qt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "portrait.jpg"
            output_dir = root / "out"
            output_dir.mkdir()
            profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
            exif = Image.Exif()
            exif[COPYRIGHT_TAG] = "NDEX Smoke"
            exif[GPS_TAG] = {1: "N", 2: (40.0, 0.0, 0.0), 3: "W", 4: (88.0, 0.0, 0.0)}
            Image.new("RGB", (120, 180), (30, 60, 90)).save(
                source, format="JPEG", quality=95, icc_profile=profile.tobytes(), exif=exif
            )
            stdout = io.StringIO()
            with patch("ndex_frame.main.QApplication") as qapplication, patch("sys.stdout", stdout):
                code = main(["--smoke-export", str(source), str(output_dir)])

            qapplication.assert_not_called()
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue().strip().splitlines()[-1])
            destination = Path(payload["items"][0]["destination"])
            self.assertTrue(destination.is_file())
            with Image.open(destination) as exported:
                self.assertEqual(exported.format, "JPEG")
                self.assertEqual(exported.size, (1080, 1440))
                self.assertTrue(exported.info.get("icc_profile"))
                tags = exported.getexif()
                self.assertEqual(tags.get(COPYRIGHT_TAG), "NDEX Smoke")
                self.assertNotIn(GPS_TAG, tags)


if __name__ == "__main__":
    unittest.main()
