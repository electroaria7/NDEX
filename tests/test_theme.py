from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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

    def test_header_identifies_the_app_with_or_without_the_wordmark(self) -> None:
        root = tk.Tk()
        self.addCleanup(root.destroy)
        theme.apply_tk_theme(root)
        for image in (None, tk.PhotoImage(master=root, width=305, height=58)):
            with self.subTest(has_image=image is not None), patch.object(theme, "load_brand_image", return_value=image):
                holder: list[tk.PhotoImage] = []
                header = theme.build_app_header(root, title="NDEX One", tagline="Backup", holder=holder)
                header.pack()
                root.update_idletasks()
                labels = [child for child in header.winfo_children() if isinstance(child, ttk.Label)]
                self.assertIn("NDEX One", [label.cget("text") for label in labels])
                if image is not None:
                    self.assertLessEqual(holder[-1].height(), 24)
                    self.assertLessEqual(holder[-1].width(), 122)
                header.destroy()

    def test_window_icon_supplies_multiple_sizes(self) -> None:
        root = tk.Tk()
        self.addCleanup(root.destroy)
        holder = []
        with patch.object(root, "iconphoto") as iconphoto:
            theme.apply_window_icon(root, holder)
        self.assertEqual([icon.width() for icon in holder], [16, 24, 32, 48, 64])
        iconphoto.assert_called_once_with(True, *holder)

    def test_header_tagline_uses_its_allocated_width_and_respects_side_info(self) -> None:
        root = tk.Tk()
        self.addCleanup(root.destroy)
        theme.apply_tk_theme(root)
        root.geometry("880x520")
        header = theme.build_app_header(
            root, title="NDEX Launcher",
            tagline="Start with 01 Backup. Each step hands its folder to the next.",
            holder=[], compact=True,
        )
        header.pack(fill="x")
        root.update()
        description = next(label for label in header.winfo_children()
                           if isinstance(label, ttk.Label) and str(label.cget("style")) == "Tagline.TLabel")
        reference = ttk.Label(root, text="One line", style="Tagline.TLabel")
        self.assertEqual(description.winfo_height(), reference.winfo_reqheight())
        self.assertGreater(description.winfo_width(), 600)
        info = ttk.Label(header, text="Folder status", width=28)
        info.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))
        root.update()
        self.assertLessEqual(description.winfo_x() + description.winfo_width(), info.winfo_x())
        self.assertEqual(int(description.cget("wraplength")), description.winfo_width())


class ScrollableFormTests(unittest.TestCase):
    def test_focus_reveals_options_without_moving_fixed_actions(self) -> None:
        root = tk.Tk()
        self.addCleanup(root.destroy)
        theme.apply_tk_theme(root)
        root.geometry("360x240")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        viewport = theme.ScrollableFrame(root)
        viewport.grid(row=0, column=0, sticky="nsew")
        for index in range(20):
            option = ttk.Entry(viewport.content)
            option.pack(pady=3)
        action = ttk.Button(root, text="Start")
        action.grid(row=1, column=0)
        root.update()
        action_y = action.winfo_rooty()
        self.assertTrue(viewport.scrollbar.winfo_manager())
        viewport.reveal_focused_control(SimpleNamespace(widget=option))
        root.update()
        self.assertGreaterEqual(option.winfo_rooty(), viewport.canvas.winfo_rooty())
        self.assertLessEqual(option.winfo_rooty() + option.winfo_height(), action_y)
        self.assertEqual(action.winfo_rooty(), action_y)
        # A window manager can cap a requested tall window to the desktop's
        # height. Make the form fit by reducing its content instead, keeping
        # this scrollbar check independent of the CI monitor resolution.
        for field in viewport.content.winfo_children()[:-2]:
            field.destroy()
        root.update()
        self.assertLessEqual(viewport.content.winfo_reqheight(), viewport.canvas.winfo_height())
        self.assertFalse(viewport.scrollbar.winfo_manager())
        self.assertTrue(viewport.content.winfo_ismapped())
        self.assertEqual(viewport.canvas.canvasy(0), 0)
        for field in viewport.content.winfo_children():
            self.assertGreaterEqual(field.winfo_rooty(), viewport.canvas.winfo_rooty())
            self.assertLessEqual(field.winfo_rooty() + field.winfo_height(), action_y)


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
        def buttons_in(widget):
            found = []
            for child in widget.winfo_children():
                if child.winfo_class() == "TButton":
                    found.append(child.cget("text"))
                found.extend(buttons_in(child))
            return found

        button_texts = buttons_in(first_card)
        self.assertTrue({"Open", "Continue"} & set(button_texts))
        self.assertEqual(app.cget("bg"), theme.APP_BG)

    def test_secondary_buttons_are_visibly_buttons(self) -> None:
        root = tk.Tk()
        self.addCleanup(root.destroy)
        style = theme.apply_tk_theme(root)
        face = style.lookup("TButton", "background")
        self.assertNotIn(face.lower(), (theme.APP_BG.lower(), theme.CARD_BG.lower()))
        self.assertEqual(style.lookup("TButton", "bordercolor"), theme.BUTTON_BORDER)
        self.assertNotEqual(style.lookup("TButton", "bordercolor"), theme.BORDER)
        self.assertEqual(style.lookup("Accent.TButton", "background"), theme.ACCENT)

    def test_tooltip_resolves_callable_text(self) -> None:
        root = tk.Tk()
        self.addCleanup(root.destroy)
        label = tk.Label(root, text="x")
        tip = theme.add_tooltip(label, lambda: "full path")
        self.assertEqual(tip.current_text(), "full path")


if __name__ == "__main__":
    unittest.main()
