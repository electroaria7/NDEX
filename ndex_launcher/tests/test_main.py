from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common.report import JobItem, JobReport
from ndex_launcher.main import COMPACT_LAYOUT_WIDTH, LauncherApp, uses_compact_card_layout


class LauncherLayoutTests(unittest.TestCase):
    def test_compact_layout_threshold_is_1100px(self) -> None:
        self.assertTrue(uses_compact_card_layout(COMPACT_LAYOUT_WIDTH - 1))
        self.assertFalse(uses_compact_card_layout(COMPACT_LAYOUT_WIDTH))

    def test_creates_four_workflow_cards(self) -> None:
        app = LauncherApp()
        self.addCleanup(app.destroy)
        app.update_idletasks()

        self.assertEqual(
            list(app._cards),
            ["ndex_one", "image_manager", "auto_selector", "frame"],
        )

    def test_wide_layout_places_four_cards_in_one_row(self) -> None:
        app = LauncherApp()
        self.addCleanup(app.destroy)
        app.geometry(f"{COMPACT_LAYOUT_WIDTH}x560")
        app.update_idletasks()
        app._apply_card_layout(COMPACT_LAYOUT_WIDTH)

        rows = {int(card.grid_info()["row"]) for card in app._cards.values()}
        columns = [int(app._cards[key].grid_info()["column"]) for key in app._cards]
        self.assertEqual(rows, {0})
        self.assertEqual(columns, [0, 2, 4, 6])
        self.assertEqual(len(app._arrows), 3)

    def test_compact_layout_uses_two_by_two_grid_without_arrows(self) -> None:
        app = LauncherApp()
        self.addCleanup(app.destroy)
        app.geometry("980x560")
        app.update_idletasks()
        app._apply_card_layout(980)

        positions = [
            (int(app._cards[key].grid_info()["row"]), int(app._cards[key].grid_info()["column"]))
            for key in app._cards
        ]
        self.assertEqual(positions, [(0, 0), (0, 1), (1, 0), (1, 1)])
        self.assertEqual(app._arrows, [])

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
