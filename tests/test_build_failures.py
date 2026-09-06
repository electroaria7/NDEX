"""Execute build wrappers with failing tools; stale artifacts must not ship."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == "nt", "PowerShell build wrappers run on Windows")
class BuildFailureTests(unittest.TestCase):
    def test_app_builds_propagate_tool_failure(self):
        repo = Path(__file__).resolve().parents[1]
        scripts = ("build/build.ps1", "dsb_image_manager/build_package.ps1",
                   "ndex_auto_selector/build_package.ps1", "ndex_launcher/build_package.ps1",
                   "ndex_frame/build_package.ps1")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "python.cmd").write_text("@exit /b 42\n")
            (root / "ndex_common").mkdir()
            shutil.copy2(repo / "ndex_common/version.py", root / "ndex_common/version.py")
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"])
            for relative in scripts:
                with self.subTest(script=relative):
                    target = root / relative
                    target.parent.mkdir(exist_ok=True)
                    shutil.copy2(repo / relative, target)
                    result = subprocess.run(["powershell", "-NoProfile", "-File", str(target)],
                                            cwd=root, env=env, capture_output=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0, result.stdout.decode(errors="replace"))

    def test_release_stops_before_assembling_stale_executables(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ndex_common").mkdir()
            shutil.copy2(repo / "ndex_common/version.py", root / "ndex_common/version.py")
            shutil.copy2(repo / "build_all.ps1", root / "build_all.ps1")
            (root / "build").mkdir()
            (root / "build/build.ps1").write_text("exit 42\n")
            result = subprocess.run(["powershell", "-NoProfile", "-File", str(root / "build_all.ps1")],
                                    cwd=root, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"App build failed", result.stderr)
            self.assertFalse((root / "release").exists())
