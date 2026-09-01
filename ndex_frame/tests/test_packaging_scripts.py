from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRAME_ROOT = Path(__file__).resolve().parents[1]


def _ndex_version() -> str:
    text = (REPO_ROOT / "ndex_common" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'NDEX_VERSION = "([^"]+)"', text)
    assert match is not None
    return match.group(1)


class PackagingScriptTests(unittest.TestCase):
    def test_frame_build_script_uses_windowed_pyinstaller_and_version_resource(self) -> None:
        script = (FRAME_ROOT / "build_package.ps1").read_text(encoding="utf-8")
        required = (
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name NDEX_Frame",
            "--collect-submodules ndex_frame",
            "--collect-submodules ndex_common",
            "--collect-all PySide6",
            "--hidden-import PIL.ImageCms",
            r"$appRoot\resources;ndex_frame\resources",
            r"$repoRoot\assets\branding;assets\branding",
            r"$repoRoot\assets\branding\ndex_icon.ico",
            "--version-file",
            "NDEX Frame",
            "NDEX_Frame",
            "NDEX Frame - photography framing and export",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, script)

    def test_packaged_smoke_script_checks_export_invariants(self) -> None:
        script = (FRAME_ROOT / "tests" / "smoke_packaged.ps1").read_text(encoding="utf-8")
        required = (
            "NDEX_Frame.exe",
            "--smoke-export",
            "1200",
            "1800",
            "1080",
            "1440",
            "copyright",
            "GPS",
            "SHA256",
            "icc",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, script)

    def test_release_builder_includes_frame_as_fourth_of_five_apps(self) -> None:
        script = (REPO_ROOT / "build_all.ps1").read_text(encoding="utf-8")
        self.assertIn("[1/5]", script)
        self.assertIn("[2/5]", script)
        self.assertIn("[3/5]", script)
        self.assertIn("[4/5]", script)
        self.assertIn("[5/5]", script)
        self.assertNotIn("[1/4]", script)
        self.assertIn(r"ndex_frame\build_package.ps1", script)
        self.assertIn(r'@{ Source = "ndex_frame\dist\NDEX_Frame.exe"; Target = "NDEX_Frame.exe" }', script)
        frame_index = script.index(r"ndex_frame\build_package.ps1")
        launcher_index = script.index(r"ndex_launcher\build_package.ps1")
        self.assertLess(frame_index, launcher_index)

    def test_frame_build_always_installs_pinned_pyinstaller(self) -> None:
        script = (FRAME_ROOT / "build_package.ps1").read_text(encoding="utf-8")
        self.assertIn('python -m pip install "pyinstaller==6.11.1"', script)
        self.assertNotIn('python -c "import PyInstaller"', script)

    def test_ndex_one_build_upgrades_pinned_pyinstaller(self) -> None:
        script = (REPO_ROOT / "build" / "build.ps1").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertIn('python -m pip install --upgrade "pyinstaller==6.11.1"', script)
        self.assertNotIn("python -m pip install --upgrade pyinstaller\n", script)

    def test_suite_installer_installs_all_apps_into_ndex_folder(self) -> None:
        script = (REPO_ROOT / "build" / "installer.iss").read_text(encoding="utf-8")
        version = _ndex_version()
        self.assertIn('#define MyAppName "NDEX"', script)
        self.assertIn(f'#define MyAppVersion "{version}"', script)
        self.assertIn('#define MyAppExeName "NDEX_Launcher.exe"', script)
        self.assertIn(r"DefaultDirName={autopf}\NDEX", script)
        self.assertIn("DefaultGroupName=NDEX", script)
        self.assertIn(rf"release\NDEX_v{version}", script.replace("/", "\\"))
        self.assertIn("NDEX_Launcher.exe", script)
        self.assertIn("NDEX_One_OneFile.exe", script)
        self.assertIn("NDEX_Image_Manager.exe", script)
        self.assertIn("NDEX_Auto_Selector.exe", script)
        self.assertIn("NDEX_Frame.exe", script)
        self.assertIn("1. Backup - NDEX One", script)
        self.assertIn("2. Select & Rate - Image Manager", script)
        self.assertIn("3. Extract - Auto Selector", script)
        self.assertIn("4. Frame & Export - NDEX Frame", script)
        self.assertIn(f"NDEX_Setup_{version}", script)
        self.assertNotIn(r"dist\NDEX_One\*", script)
        self.assertNotIn('#define MyAppName "NDEX One"', script)

    def test_release_builder_compiles_suite_installer_from_release_folder(self) -> None:
        script = (REPO_ROOT / "build_all.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$Installer", script)
        self.assertIn("installer.iss", script)
        self.assertIn("ISCC", script)
        self.assertIn("ndex_frame\\PATCH_NOTES.md", script)


if __name__ == "__main__":
    unittest.main()
