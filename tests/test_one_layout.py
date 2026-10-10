from __future__ import annotations

import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.gui import DSBApp, STOPPING_STATUS


class OneLayoutTests(unittest.TestCase):
    def test_short_window_keeps_actions_visible_and_all_options_reachable(self) -> None:
        original_init = tk.Tk.__init__
        for scaling in (4 / 3, 2.0):
            with self.subTest(scaling=scaling), tempfile.TemporaryDirectory() as tmp:
                def scaled_init(root, *args, **kwargs):
                    original_init(root, *args, **kwargs)
                    root.original_scaling = root.tk.call("tk", "scaling")
                    root.tk.call("tk", "scaling", scaling)

                with patch.dict(os.environ, {"LOCALAPPDATA": str(Path(tmp) / "appdata")}), \
                        patch.object(tk.Tk, "__init__", scaled_init):
                    app = DSBApp(preload_only=True)
                try:
                    app.geometry("1080x600")
                    for enabled in app.brand_vars.values():
                        enabled.set(True)
                    app._refresh_file_type_options()
                    app.status_var.set(STOPPING_STATUS)
                    app.update()
                    viewport = app.options_viewport
                    self.assertLessEqual(app.minsize()[1], 600)
                    self.assertTrue(viewport.scrollbar.winfo_manager())
                    actions = (app.analyze_button, app.backup_button, app.cancel_button,
                               app.results_button, app.open_button, app.handoff_button)
                    for button in actions:
                        self.assertTrue(button.winfo_ismapped())
                        self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
                        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                             app.winfo_rooty() + app.winfo_height())
                    for option in app.type_checkbuttons.values():
                        viewport.reveal_focused_control(SimpleNamespace(widget=option))
                        app.update_idletasks()
                        self.assertGreaterEqual(option.winfo_rooty(), viewport.canvas.winfo_rooty())
                        self.assertLessEqual(option.winfo_rooty() + option.winfo_height(),
                                             viewport.canvas.winfo_rooty() + viewport.canvas.winfo_height())
                        self.assertLessEqual(option.winfo_rootx() + option.winfo_width(),
                                             viewport.canvas.winfo_rootx() + viewport.canvas.winfo_width())
                finally:
                    for timer in app.tk.call("after", "info"):
                        app.after_cancel(timer)
                    app.tk.call("tk", "scaling", app.original_scaling)
                    app.destroy()


if __name__ == "__main__":
    unittest.main()
