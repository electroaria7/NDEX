"""NDEX One and Auto Selector build in another language and keep settings keys intact."""

from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common import i18n
from ndex_common.settings import get_section, update_section

FAKE = {
    "__meta__": {"name": "Fake", "code": "xx"},
    "Source Folder": "XX Source Folder",
    "Analyze": "XX Analyze",
    "Overwrite existing": "XX Overwrite existing",
    "Original RAW folder": "XX Original RAW folder",
    "Analyze Matches": "XX Analyze Matches",
    "Skip existing": "XX Skip existing",
    "__plural__": {
        "{count} file": ["XX {count} file", "XX {count} files"],
        "{count} photo picked in Image Manager (from {folder})": ["XX {count} pick ({folder})"],
    },
}


def _texts(widget: tk.Misc) -> set[str]:
    found: set[str] = set()
    for child in [widget, *widget.winfo_children()]:
        try:
            found.add(str(child.cget("text")))
        except tk.TclError:
            pass
        if child is not widget:
            found |= _texts(child)
    return found


class LocalizedAppTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "appdata")})
        env.start()
        self.addCleanup(env.stop)
        locales = i18n.override_locales_dir()
        locales.mkdir(parents=True, exist_ok=True)
        (locales / "xx.json").write_text(json.dumps(FAKE, ensure_ascii=False), encoding="utf-8")
        self.addCleanup(i18n.init, "test", "en")

    def _destroy(self, app: tk.Tk) -> None:
        try:
            for timer in app.tk.call("after", "info"):
                app.after_cancel(timer)
            app.destroy()
        except Exception:
            pass

    def test_ndex_one_shows_translations_and_keeps_saved_keys(self) -> None:
        from src.config import ConfigManager
        from src.gui import DSBApp

        manager = ConfigManager()
        settings = manager.load()
        settings["duplicate_policy"] = "overwrite"
        settings["verify_mode"] = "sha256"
        manager.save(settings)

        i18n.init("ndex_one", "xx")
        app = DSBApp(preload_only=True)
        app.withdraw()
        self.addCleanup(self._destroy, app)
        texts = _texts(app)
        self.assertIn("XX Source Folder", texts)
        self.assertIn("XX Analyze", texts)
        self.assertEqual(app.duplicate_var.get(), "XX Overwrite existing")
        self.assertEqual(app._selected_duplicate_policy(), "overwrite")
        app._save_settings()
        saved = ConfigManager().load()
        self.assertEqual(saved["duplicate_policy"], "overwrite")
        self.assertEqual(saved["verify_mode"], "sha256")

        # Back in English the same saved values give the English labels again.
        i18n.init("ndex_one", "en")
        again = DSBApp(preload_only=True)
        again.withdraw()
        self.addCleanup(self._destroy, again)
        self.assertEqual(again.duplicate_var.get(), "Overwrite existing")
        self.assertEqual(again._selected_verify_mode(), "sha256")

    def test_auto_selector_shows_translations_and_keeps_saved_keys(self) -> None:
        from ndex_auto_selector.ndex_auto_selector.ui.tk_app import AutoSelectorApp, handoff_text

        update_section("auto_selector", {"duplicate_policy": "skip"})
        i18n.init("auto_selector", "xx")
        app = AutoSelectorApp()
        app.withdraw()
        self.addCleanup(self._destroy, app)
        texts = _texts(app)
        self.assertIn("XX Original RAW folder", texts)
        self.assertIn("XX Analyze Matches", texts)
        self.assertEqual(app.duplicate_var.get(), "skip")
        self.assertEqual(app.duplicate_label_var.get(), "XX Skip existing")
        self.assertEqual(app._copy_options()["duplicate_policy"], "skip")
        self.assertEqual(handoff_text(1, "D:\\a"), "XX 1 pick (D:\\a)")
        self.assertEqual(get_section("auto_selector")["duplicate_policy"], "skip")

    def test_path_entries_have_full_path_tooltips(self) -> None:
        from ndex_auto_selector.ndex_auto_selector.ui.tk_app import AutoSelectorApp

        app = AutoSelectorApp()
        app.withdraw()
        self.addCleanup(self._destroy, app)
        app.raw_source_var.set("C:/very/long/raw/folder")
        bindings = app.raw_entry.bind("<Enter>")
        self.assertTrue(bindings)
        app.work_folder_var.set("D:/work")
        self.assertTrue(app.work_entry.bind("<Enter>"))

    def test_report_text_is_translated_at_display_time(self) -> None:
        from ndex_common.report import JobReport

        i18n.init("t", "xx")
        report = JobReport(Path("m.json"), "backup", "ndex_one", "bad-time", counts={})
        self.assertEqual(report.count_summary, "nothing recorded")


if __name__ == "__main__":
    unittest.main()
