from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common import launch as launch_mod


class LaunchResolutionTests(unittest.TestCase):
    def assertSameFile(self, actual: Path | None, expected: Path) -> None:
        self.assertIsNotNone(actual)
        if actual is not None:
            self.assertTrue(actual.samefile(expected))

    def test_frozen_launcher_finds_apps_folder_executables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apps = root / "Apps"
            apps.mkdir()
            frame = apps / "NDEX_Frame.exe"
            frame.write_bytes(b"MZ")
            launcher = root / "NDEX_Launcher.exe"
            launcher.write_bytes(b"MZ")
            with (
                patch.object(launch_mod.sys, "frozen", True, create=True),
                patch.object(launch_mod.sys, "executable", str(launcher)),
                patch.object(launch_mod, "_repo_root", return_value=None),
            ):
                found = launch_mod._find_executable("NDEX_Frame.exe")
            self.assertSameFile(found, frame)

    def test_frozen_launcher_accepts_ndex_one_onefile_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apps = root / "Apps"
            apps.mkdir()
            one = apps / "NDEX_One_OneFile.exe"
            one.write_bytes(b"MZ")
            launcher = root / "NDEX_Launcher.exe"
            launcher.write_bytes(b"MZ")
            with (
                patch.object(launch_mod.sys, "frozen", True, create=True),
                patch.object(launch_mod.sys, "executable", str(launcher)),
                patch.object(launch_mod, "_repo_root", return_value=None),
            ):
                found = launch_mod._find_executable("NDEX_One.exe")
            self.assertSameFile(found, one)

    def test_app_commands_use_stable_ndex_one_name(self) -> None:
        self.assertEqual(launch_mod.APP_COMMANDS["ndex_one"][0], "NDEX_One.exe")
        self.assertEqual(launch_mod.APP_COMMANDS["frame"][0], "NDEX_Frame.exe")

    def test_frozen_app_in_apps_folder_finds_sibling_exe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            apps = Path(tmp) / "Apps"
            apps.mkdir()
            one = apps / "NDEX_One.exe"
            manager = apps / "NDEX_Image_Manager.exe"
            one.write_bytes(b"MZ")
            manager.write_bytes(b"MZ")
            with (
                patch.object(launch_mod.sys, "frozen", True, create=True),
                patch.object(launch_mod.sys, "executable", str(one)),
                patch.object(launch_mod, "_repo_root", return_value=None),
            ):
                found = launch_mod._find_executable("NDEX_Image_Manager.exe")
            self.assertSameFile(found, manager)

    def test_frozen_search_does_not_use_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decoy = root / "NDEX_Frame.exe"
            nested = root / "nested"
            nested.mkdir()
            decoy.write_bytes(b"MZ")
            launcher = nested / "NDEX_Launcher.exe"
            launcher.write_bytes(b"MZ")
            with (
                patch.object(launch_mod.sys, "frozen", True, create=True),
                patch.object(launch_mod.sys, "executable", str(launcher)),
                patch.object(launch_mod, "_repo_root", return_value=None),
            ):
                found = launch_mod._find_executable("NDEX_Frame.exe")
            self.assertIsNone(found)

    def test_frozen_does_not_search_repo_dist_or_run_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            (dist / "NDEX_Frame.exe").write_bytes(b"MZ")
            launcher = root / "NDEX_Launcher.exe"
            launcher.write_bytes(b"MZ")
            with (
                patch.object(launch_mod.sys, "frozen", True, create=True),
                patch.object(launch_mod.sys, "executable", str(launcher)),
                patch.object(launch_mod, "_repo_root", return_value=root),
                patch.object(launch_mod.subprocess, "Popen") as popen,
            ):
                found = launch_mod._find_executable("NDEX_Frame.exe")
                launched = launch_mod.launch_app("frame")
            self.assertIsNone(found)
            self.assertFalse(launched)
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
