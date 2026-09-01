from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common import launch as launch_mod


class LaunchResolutionTests(unittest.TestCase):
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
            self.assertEqual(found, frame)

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
            self.assertEqual(found, one)

    def test_app_commands_use_stable_ndex_one_name(self) -> None:
        self.assertEqual(launch_mod.APP_COMMANDS["ndex_one"][0], "NDEX_One.exe")
        self.assertEqual(launch_mod.APP_COMMANDS["frame"][0], "NDEX_Frame.exe")


if __name__ == "__main__":
    unittest.main()
