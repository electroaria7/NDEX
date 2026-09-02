from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import main as ndex_one_main
from dsb_image_manager import main as image_manager_main
from ndex_auto_selector import main as auto_selector_main
from ndex_frame.main import build_parser as frame_parser


class OpenFlagTests(unittest.TestCase):
    def test_ndex_one_open_preloads_gui_instead_of_cli(self) -> None:
        args = ndex_one_main.build_parser().parse_args(
            ["--open", "--source", "E:/DCIM", "--destination", "D:/Lib", "--backup"]
        )
        self.assertTrue(args.open)
        self.assertTrue(args.backup)
        with (
            patch.object(ndex_one_main, "run_app") as run_app,
            patch.object(ndex_one_main, "run_cli") as run_cli,
            patch.object(ndex_one_main, "install_crash_logging"),
            patch("sys.argv", ["NDEX_One", "--open", "--source", "E:/DCIM", "--destination", "D:/Lib"]),
        ):
            code = ndex_one_main.main()
        self.assertEqual(code, 0)
        run_app.assert_called_once()
        run_cli.assert_not_called()
        kwargs = run_app.call_args.kwargs
        self.assertEqual(kwargs["initial_source"], Path("E:/DCIM"))
        self.assertEqual(kwargs["initial_destination"], Path("D:/Lib"))

    def test_image_manager_open_skips_cli_scan(self) -> None:
        args = image_manager_main.build_parser().parse_args(["--open", "--source", "D:/Lib"])
        self.assertTrue(args.open)
        self.assertEqual(args.source, Path("D:/Lib"))

    def test_auto_selector_open_preloads_folders(self) -> None:
        args = auto_selector_main.build_parser().parse_args(
            ["--open", "--selected-jpg", "D:/JPG", "--raw-source", "D:/RAW", "--work-folder", "D:/Work"]
        )
        self.assertTrue(args.open)
        self.assertEqual(args.work_folder, Path("D:/Work"))

    def test_frame_open_accepts_handoff(self) -> None:
        args = frame_parser().parse_args(["--open", "--handoff", "select.json", "--output", "framed"])
        self.assertTrue(args.open)
        self.assertEqual(args.handoff, Path("select.json"))
        self.assertEqual(args.output, Path("framed"))


if __name__ == "__main__":
    unittest.main()
