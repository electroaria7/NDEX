from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRAME_ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
