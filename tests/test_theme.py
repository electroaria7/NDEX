from __future__ import annotations

import tkinter as tk
import unittest

from ndex_common import theme
from ndex_launcher.main import COMPACT_LAYOUT_WIDTH, LauncherApp
from ndex_launcher.state import gather_workflow_state


class ThemeTokenTests(unittest.TestCase):
    def test_suite_shares_one_light_palette(self) -> None:
        self.assertEqual(theme.APP_BG, "#F3F5F9")
        self.assertEqual(theme.CARD_BG, "#FFFFFF")
        self.assertEqual(theme.ACCENT, "#2563EB")
        self.assertTrue(theme.qt_stylesheet().startswith("\n" + "/* NDEX-THEME */") or "NDEX-THEME" in theme.qt_stylesheet())
        self.assertIn("QPushButton#primaryButton", theme.qt_stylesheet())
        self.assertIn(theme.PREVIEW_WELL, theme.qt_stylesheet())

    def test_apply_tk_theme_registers_shared_styles(self) -> None:
        root = tk.Tk()
        self.addCleanup(root.destroy)
        style = theme.apply_tk_theme(root)
        self.assertEqual(root.cget("bg"), theme.APP_BG)
        self.assertEqual(style.lookup("Accent.TButton", "background"), theme.ACCENT)
        self.assertEqual(style.lookup("Card.TFrame", "background"), theme.CARD_BG)
        font = str(style.lookup("Title.TLabel", "font"))
        self.assertIn("Segoe UI", font)
        self.assertIn("18", font)
        self.assertIn("bold", font)

    def test_build_app_header_falls_back_to_title_text(self) -> None:
        root = tk.Tk()
        self.addCleanup(root.destroy)
        theme.apply_tk_theme(root)
        holder: list[tk.PhotoImage] = []
        header = theme.build_app_header(root, title="NDEX One", tagline="Backup", holder=holder)
        header.pack()
        root.update_idletasks()
        labels = [child for child in header.winfo_children() if isinstance(child, tk.Widget)]
        self.assertGreaterEqual(len(labels), 1)


class ThemedLauncherTests(unittest.TestCase):
    def test_workflow_cards_use_short_titles_and_accent_open(self) -> None:
        steps = gather_workflow_state()
        self.assertEqual([step.short_title for step in steps], ["Backup", "Select & Rate", "Extract", "Frame & Export"])
        self.assertEqual([step.number for step in steps], ["01", "02", "03", "04"])

        app = LauncherApp()
        self.addCleanup(app.destroy)
        app.geometry(f"{COMPACT_LAYOUT_WIDTH}x620")
        app.update_idletasks()
        app._apply_card_layout(COMPACT_LAYOUT_WIDTH)
        app.refresh_status()

        first_card = app._cards["ndex_one"]
        button_texts = [child.cget("text") for child in first_card.winfo_children() if child.winfo_class() == "TButton"]
        self.assertIn("Open", button_texts)
        self.assertEqual(app.cget("bg"), theme.APP_BG)


if __name__ == "__main__":
    unittest.main()
