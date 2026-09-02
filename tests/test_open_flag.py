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

    def test_ndex_one_open_empty_does_not_reuse_remembered_folders(self) -> None:
        with (
            patch.object(ndex_one_main, "run_app") as run_app,
            patch.object(ndex_one_main, "run_cli") as run_cli,
            patch.object(ndex_one_main, "install_crash_logging"),
            patch("sys.argv", ["NDEX_One", "--open"]),
        ):
            code = ndex_one_main.main()
        self.assertEqual(code, 0)
        run_cli.assert_not_called()
        kwargs = run_app.call_args.kwargs
        self.assertTrue(kwargs["preload_only"])
        self.assertIsNone(kwargs["initial_source"])
        self.assertIsNone(kwargs["initial_destination"])

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


class RetryFlagTests(unittest.TestCase):
    """The Launcher's "Retry in app..." lands here: --retry opens the app at that job."""

    def test_ndex_one_retry_opens_the_gui_at_that_manifest(self) -> None:
        with (
            patch.object(ndex_one_main, "run_app") as run_app,
            patch.object(ndex_one_main, "run_cli") as run_cli,
            patch.object(ndex_one_main, "install_crash_logging"),
            patch("sys.argv", ["NDEX_One", "--open", "--retry", "C:/m/backup-1.json"]),
        ):
            code = ndex_one_main.main()
        self.assertEqual(code, 0)
        run_cli.assert_not_called()
        self.assertEqual(run_app.call_args.kwargs["retry_manifest"], Path("C:/m/backup-1.json"))
        self.assertTrue(run_app.call_args.kwargs["preload_only"])

    def test_ndex_one_retry_alone_still_means_the_gui(self) -> None:
        with (
            patch.object(ndex_one_main, "run_app") as run_app,
            patch.object(ndex_one_main, "run_cli") as run_cli,
            patch.object(ndex_one_main, "install_crash_logging"),
            patch("sys.argv", ["NDEX_One", "--retry", "C:/m/backup-1.json"]),
        ):
            ndex_one_main.main()
        run_cli.assert_not_called()
        run_app.assert_called_once()

    def test_auto_selector_retry_opens_the_gui_at_that_manifest(self) -> None:
        with (
            patch.object(auto_selector_main, "run_app") as run_app,
            patch.object(auto_selector_main, "install_crash_logging"),
            patch("sys.argv", ["NDEX_Auto_Selector", "--open", "--retry", "C:/m/extract-1.json"]),
        ):
            code = auto_selector_main.main()
        self.assertEqual(code, 0)
        self.assertEqual(run_app.call_args.kwargs["retry_manifest"], Path("C:/m/extract-1.json"))

    def test_frame_accepts_retry(self) -> None:
        args = frame_parser().parse_args(["--open", "--retry", "export-1.json"])
        self.assertEqual(args.retry, Path("export-1.json"))


if __name__ == "__main__":
    unittest.main()
