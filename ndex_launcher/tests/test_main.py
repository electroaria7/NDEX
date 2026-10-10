from __future__ import annotations

import tempfile
import unittest
from tkinter import ttk
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from ndex_common.report import JobItem, JobReport
from ndex_launcher.main import COMPACT_LAYOUT_WIDTH, LauncherApp, uses_compact_card_layout
from ndex_launcher.state import StepState


class LauncherLayoutTests(unittest.TestCase):
    def _steps(self, **overrides):
        fields = {
            "description": "Copy camera files into the date-based library.",
            "last_folder": "C:/" + "long photo folder/" * 25,
            "launch_args": ["--continue"],
        }
        fields.update(overrides)
        return [StepState(key=str(i), title=f"{i}. Backup", **fields) for i in range(4)]

    def _assert_cards_fit(self, app) -> None:
        canvas_height = app._canvas.winfo_height()
        self.assertLessEqual(app._body.winfo_reqheight(), canvas_height)
        self.assertFalse(app._scrollbar.winfo_manager())
        for card in app._cards.values():
            for button in (w for w in card.winfo_children()[-1].winfo_children() if isinstance(w, ttk.Button)):
                self.assertTrue(button.winfo_ismapped())
                self.assertLessEqual(
                    button.winfo_rooty() + button.winfo_height(),
                    app._canvas.winfo_rooty() + canvas_height,
                )

    def test_every_card_and_button_fits_at_default_and_minimum_size(self) -> None:
        with patch("ndex_launcher.main.gather_workflow_state", return_value=self._steps()):
            app = LauncherApp()
            self.addCleanup(app.destroy)
            for size in ("880x520", "1040x620", "1200x560"):
                with self.subTest(size=size):
                    app.geometry(size)
                    app.refresh_status()
                    app.update()
                    self._assert_cards_fit(app)
                    footer = app.grid_slaves(row=2)[0]
                    self.assertLessEqual(footer.winfo_y() + footer.winfo_height(), app.winfo_height())
                    self.assertGreater(footer.winfo_height(), 1)

    def test_scrolling_remains_a_fallback_when_the_window_is_too_short(self) -> None:
        with patch("ndex_launcher.main.gather_workflow_state", return_value=self._steps()):
            app = LauncherApp()
            self.addCleanup(app.destroy)
            app.minsize(300, 200)
            app.geometry("880x300")
            app.refresh_status()
            app.update()
            self.assertGreater(app._body.winfo_reqheight(), app._canvas.winfo_height())
            self.assertTrue(app._scrollbar.winfo_manager())
            button = list(app._cards.values())[-1].winfo_children()[-1].winfo_children()[-1]
            app._reveal_focused_control(SimpleNamespace(widget=button))
            app.update()
            self.assertGreaterEqual(button.winfo_rooty(), app._canvas.winfo_rooty())

    def test_compact_layout_threshold_is_the_minimum_window_width(self) -> None:
        self.assertEqual(COMPACT_LAYOUT_WIDTH, 880)
        self.assertTrue(uses_compact_card_layout(COMPACT_LAYOUT_WIDTH - 1))
        self.assertFalse(uses_compact_card_layout(COMPACT_LAYOUT_WIDTH))
        self.assertFalse(uses_compact_card_layout(1040))

    def test_creates_four_workflow_cards(self) -> None:
        app = LauncherApp()
        self.addCleanup(app.destroy)
        app.update_idletasks()

        self.assertEqual(
            list(app._cards),
            ["ndex_one", "image_manager", "auto_selector", "frame"],
        )

    def test_one_row_layout_is_used_from_the_minimum_width_up(self) -> None:
        app = LauncherApp()
        self.addCleanup(app.destroy)
        for size in ("880x520", "1040x620"):
            with self.subTest(size=size):
                app.geometry(size)
                app.update()
                rows = {int(card.grid_info()["row"]) for card in app._cards.values()}
                columns = [int(app._cards[key].grid_info()["column"]) for key in app._cards]
                self.assertEqual(rows, {0})
                self.assertEqual(columns, [0, 2, 4, 6])
                self.assertEqual(len(app._arrows), 3)

    def test_below_the_threshold_uses_two_by_two_grid_without_arrows(self) -> None:
        app = LauncherApp()
        self.addCleanup(app.destroy)
        app.update_idletasks()
        app._apply_card_layout(COMPACT_LAYOUT_WIDTH - 1)

        positions = [
            (int(app._cards[key].grid_info()["row"]), int(app._cards[key].grid_info()["column"]))
            for key in app._cards
        ]
        self.assertEqual(positions, [(0, 0), (0, 1), (1, 0), (1, 1)])
        self.assertEqual(app._arrows, [])


class CardWordingTests(unittest.TestCase):
    def _labels(self, widget):
        found = []
        for child in widget.winfo_children():
            if isinstance(child, ttk.Label):
                found.append(child)
            found.extend(self._labels(child))
        return found

    def _app_with(self, steps):
        with patch("ndex_launcher.main.gather_workflow_state", return_value=steps):
            app = LauncherApp()
        self.addCleanup(app.destroy)
        app.update()
        return app

    def test_card_shows_the_folder_name_and_keeps_the_path_for_the_tooltip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "2026-10-10 Trip"
            folder.mkdir()
            step = StepState(key="ndex_one", title="1. Backup", description="d",
                             last_folder=str(folder), launch_args=["--continue"])
            app = self._app_with([step])
            texts = [label.cget("text") for label in self._labels(app._cards["ndex_one"])]
        self.assertIn("Last: 2026-10-10 Trip", texts)
        self.assertFalse(any(tmp in text for text in texts))
        self.assertEqual(step.status_tooltip, str(folder))

    def test_continue_cards_offer_start_fresh(self) -> None:
        step = StepState(key="ndex_one", title="1. Backup", description="d", launch_args=["--continue"])
        app = self._app_with([step])
        buttons = [w.cget("text") for w in app._cards["ndex_one"].winfo_children()[-1].winfo_children()]
        self.assertEqual(buttons, ["Continue", "Start Fresh"])

    def test_problem_results_use_the_danger_style(self) -> None:
        bad = JobReport(manifest_path=Path("b.json"), type="backup", app="ndex_one",
                        created_at="2026-10-10T08:30:00Z", counts={"copied": 2, "failed": 1})
        good = JobReport(manifest_path=Path("g.json"), type="backup", app="ndex_one",
                         created_at="2026-10-10T08:30:00Z", counts={"copied": 2})
        for report, style in ((bad, "CardDanger.TLabel"), (good, "CardFaint.TLabel")):
            with self.subTest(style=style):
                step = StepState(key="ndex_one", title="1. Backup", description="d", last_result=report)
                app = self._app_with([step])
                styles = {str(l.cget("style")): l.cget("text") for l in self._labels(app._cards["ndex_one"])}
                self.assertIn(style, styles)
                self.assertEqual(styles[style].startswith("\u26a0"), report is bad)

    def test_tagline_and_settings_footer_wording(self) -> None:
        app = self._app_with([])
        texts = [label.cget("text") for label in self._labels(app)]
        self.assertIn("Start with 01 Backup. Each step hands its folder to the next.", texts)
        self.assertIn("Settings file", texts)
        self.assertFalse(any(text.startswith("Shared settings:") for text in texts))


class RetryInAppTests(unittest.TestCase):
    def test_the_launcher_opens_the_owning_app_at_that_job(self) -> None:
        app = LauncherApp()
        self.addCleanup(app.destroy)
        report = JobReport(
            manifest_path=Path("C:/m/backup-1.json"),
            type="backup",
            app="ndex_one",
            created_at="2026-09-02T10:15:00Z",
            items=(JobItem(path="E:/DCIM/a.CR3", status="failed"),),
        )
        with patch("ndex_launcher.main.launch_app", return_value=True) as launch:
            app.retry_in_app(report)
        launch.assert_called_once_with("ndex_one", ["--open", "--retry", str(Path("C:/m/backup-1.json"))])



if __name__ == "__main__":
    unittest.main()
