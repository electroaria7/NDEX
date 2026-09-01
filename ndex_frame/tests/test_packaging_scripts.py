from __future__ import annotations

import re
import subprocess
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
        self.assertIn(r'@{ Source = "ndex_frame\dist\NDEX_Frame.exe"; Target = "Apps\NDEX_Frame.exe" }', script)
        self.assertIn(r'Target = "Apps\NDEX_One.exe"', script)
        self.assertIn(r'Target = "NDEX_Launcher.exe"', script)
        self.assertIn('Join-Path $releaseDir "Docs"', script)
        self.assertIn("README.ko.md", script)
        self.assertIn("PATCH_NOTES.md", script)
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
        self.assertIn(r"{app}\NDEX_Launcher.exe", script)
        self.assertIn(r"{app}\Apps\NDEX_One.exe", script)
        self.assertIn(r"{app}\Apps\NDEX_Image_Manager.exe", script)
        self.assertIn(r"{app}\Apps\NDEX_Auto_Selector.exe", script)
        self.assertIn(r"{app}\Apps\NDEX_Frame.exe", script)
        self.assertNotIn("NDEX_One_OneFile.exe", script)
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
        self.assertIn("README.ko.md", script)
        self.assertIn("LICENSE", script)
        self.assertIn("TERMS.md", script)

    def test_installer_shows_user_agreement_in_english_and_korean(self) -> None:
        script = (REPO_ROOT / "build" / "installer.iss").read_text(encoding="utf-8")
        self.assertIn("TERMS.md", script)
        self.assertIn("TERMS.ko.md", script)
        self.assertIn("LicenseFile", script)

    def test_license_and_terms_are_free_open_source(self) -> None:
        license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        terms = (REPO_ROOT / "TERMS.md").read_text(encoding="utf-8")
        terms_ko = (REPO_ROOT / "TERMS.ko.md").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        self.assertIn("free of charge", terms.lower())
        self.assertIn("MIT License", terms)
        self.assertIn("AS IS", terms)
        self.assertIn("your photographs", terms.lower())
        self.assertIn("무료", terms_ko)
        self.assertIn("MIT", terms_ko)
        self.assertIn("있는 그대로", terms_ko)

    def test_english_and_korean_readmes_both_have_quick_start(self) -> None:
        english = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        korean = (REPO_ROOT / "README.ko.md").read_text(encoding="utf-8")
        self.assertIn("## Quick start", english)
        self.assertIn("## 빠른 시작", korean)
        self.assertIn("NDEX_Setup_1.0.0.exe", english)
        self.assertIn("NDEX_Setup_1.0.0.exe", korean)
        self.assertIn("Apps\\", english)
        self.assertIn("Apps\\", korean)
        self.assertIn("[한국어](README.ko.md)", english)
        self.assertIn("[English](README.md)", korean)

    def test_runtime_dependencies_require_patched_pillow(self) -> None:
        files = (
            REPO_ROOT / "requirements.txt",
            REPO_ROOT / "ndex_frame" / "requirements.txt",
            REPO_ROOT / "dsb_image_manager" / "requirements.txt",
        )
        for path in files:
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("<12.0.0", text)
                self.assertRegex(text, r"Pillow>=12\.3\.0")

    def test_readmes_send_users_to_github_releases(self) -> None:
        english = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        korean = (REPO_ROOT / "README.ko.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/electroaria7/NDEX/releases", english)
        self.assertIn("https://github.com/electroaria7/NDEX/releases", korean)
        self.assertIn("NDEX_v1.0.0.zip", english)
        self.assertIn("NDEX_v1.0.0.zip", korean)
        self.assertNotIn("distribution branch", english.lower())
        self.assertNotIn("distribution 브랜치", korean)

    def test_gitignore_excludes_generated_work_products_not_source_build_scripts(self) -> None:
        ignored = (
            ".ndex_data/config/settings.json",
            "dsb_image_manager/build/NDEX_Image_Manager.spec",
            "ndex_auto_selector/build/NDEX_Auto_Selector.spec",
            "ndex_launcher/build/NDEX_Launcher.spec",
            "ndex_frame/build/NDEX_Frame.spec",
            "ndex_frame/dist/NDEX_Frame.exe",
            "release/NDEX_v1.0.0/NDEX_Launcher.exe",
        )
        kept = (
            "build/installer.iss",
            "build/build.ps1",
            "build/NDEX_One.spec",
            "ndex_frame/build_package.ps1",
            "cleanup.ps1",
        )
        for relative in ignored:
            with self.subTest(ignored=relative):
                self.assertTrue(self._is_git_ignored(relative), relative)
        for relative in kept:
            with self.subTest(kept=relative):
                self.assertFalse(self._is_git_ignored(relative), relative)

    def test_cleanup_script_removes_app_build_dirs_and_local_data(self) -> None:
        script = (REPO_ROOT / "cleanup.ps1").read_text(encoding="utf-8")
        required = (
            r"dsb_image_manager\build",
            r"ndex_auto_selector\build",
            r"ndex_frame\build",
            r"ndex_launcher\build",
            ".ndex_data",
            r"ndex_frame\dist",
            r"build\NDEX_One.onefile",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, script)
        self.assertNotIn("installer.iss", script)

    def _is_git_ignored(self, relative: str) -> bool:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=REPO_ROOT,
            check=False,
        )
        return completed.returncode == 0


if __name__ == "__main__":
    unittest.main()
