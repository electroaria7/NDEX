from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ndex_common.branding import NDEX_LAUNCHER_TITLE
from ndex_common.crashlog import install_crash_logging
from ndex_common.launch import launch_app
from ndex_common.settings import settings_path
from ndex_common.theme import (
    apply_tk_theme,
    apply_window_icon,
    build_app_header,
)

from ndex_launcher.state import StepState, gather_workflow_state

COMPACT_LAYOUT_WIDTH = 1100


def uses_compact_card_layout(width: int) -> bool:
    return width < COMPACT_LAYOUT_WIDTH


class LauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(NDEX_LAUNCHER_TITLE)
        self.geometry("1040x620")
        self.minsize(880, 520)
        self.resizable(True, True)
        self.brand_images: list[tk.PhotoImage] = []
        apply_window_icon(self, self.brand_images)

        self.status_labels: dict[str, tk.StringVar] = {}
        self._cards: dict[str, ttk.Frame] = {}
        self._arrows: list[ttk.Label] = []
        self._compact_layout: bool | None = None
        apply_tk_theme(self)
        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        header = build_app_header(
            self,
            title=NDEX_LAUNCHER_TITLE,
            tagline="Photo workflow: backup, select, extract, frame",
            holder=self.brand_images,
        )
        header.pack(fill=tk.X)

        self._body = ttk.Frame(self, padding=(20, 4, 20, 12))
        self._body.pack(fill=tk.BOTH, expand=True)

        self._cards = {}
        self._arrows = []
        for step in gather_workflow_state():
            self._cards[step.key] = ttk.Frame(self._body, padding=18, style="Card.TFrame")
        self.bind("<Configure>", self._on_window_configure, add="+")
        self._apply_card_layout(self.winfo_width())

        footer = ttk.Frame(self, padding=(20, 0, 20, 16), style="Footer.TFrame")
        footer.pack(fill=tk.X)
        ttk.Button(footer, text="Refresh Status", command=self.refresh_status).pack(side=tk.LEFT)
        ttk.Label(
            footer,
            text=f"Shared settings: {settings_path()}",
            style="Faint.TLabel",
        ).pack(side=tk.RIGHT)

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        self._apply_card_layout(event.width)

    def _apply_card_layout(self, width: int) -> None:
        compact = uses_compact_card_layout(width)
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        for card in self._cards.values():
            card.grid_forget()
        for arrow in self._arrows:
            arrow.destroy()
        self._arrows = []
        for index in range(8):
            self._body.columnconfigure(index, weight=0, uniform="")
            self._body.rowconfigure(index, weight=0)

        cards = list(self._cards.values())
        if compact:
            positions = ((0, 0), (0, 1), (1, 0), (1, 1))
            for card, (row, column) in zip(cards, positions, strict=False):
                card.grid(row=row, column=column, sticky="nsew", padx=8, pady=8)
            for column in (0, 1):
                self._body.columnconfigure(column, weight=1, uniform="steps")
            for row in (0, 1):
                self._body.rowconfigure(row, weight=1)
            return

        for index, card in enumerate(cards):
            card.grid(row=0, column=index * 2, sticky="nsew", padx=(0, 0))
            self._body.columnconfigure(index * 2, weight=1, uniform="steps")
            if index < len(cards) - 1:
                arrow = ttk.Label(self._body, text="→", style="Arrow.TLabel")
                arrow.grid(row=0, column=index * 2 + 1, padx=8)
                self._arrows.append(arrow)
        self._body.rowconfigure(0, weight=1)

    def refresh_status(self) -> None:
        steps = gather_workflow_state()
        for step in steps:
            if step.key not in self._cards:
                self._cards[step.key] = ttk.Frame(self._body, padding=18, style="Card.TFrame")
                self._compact_layout = None
                self._apply_card_layout(self.winfo_width())
            self._render_card(step)

    def _render_card(self, step: StepState) -> None:
        card = self._cards[step.key]
        for child in card.winfo_children():
            child.destroy()

        heading = ttk.Frame(card, style="CardInner.TFrame")
        heading.pack(anchor="w", fill=tk.X)
        ttk.Label(
            heading,
            text=step.number or step.title.split(".", 1)[0],
            style="StepNumber.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            heading,
            text=step.short_title or step.title,
            style="CardTitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(card, text=step.description, style="Card.TLabel", wraplength=240, justify="left").pack(
            anchor="w", pady=(10, 12)
        )
        ttk.Label(card, text=step.status_text, style="CardMuted.TLabel", wraplength=240, justify="left").pack(
            anchor="w", pady=(0, 16)
        )

        continue_label = "Continue" if step.has_session else "Open"
        ttk.Button(
            card,
            text=continue_label,
            style="Accent.TButton",
            command=lambda s=step: self._launch(s.key, s.launch_args),
        ).pack(anchor="w", fill=tk.X)
        if step.has_session:
            ttk.Button(
                card,
                text="Open Empty",
                command=lambda s=step: self._launch(s.key, ["--open"]),
            ).pack(anchor="w", fill=tk.X, pady=(8, 0))

    def _launch(self, app_key: str, args: list[str]) -> None:
        try:
            launched = launch_app(app_key, args)
        except OSError as exc:
            messagebox.showerror(NDEX_LAUNCHER_TITLE, f"Launch failed: {exc}")
            return
        if not launched:
            messagebox.showerror(
                NDEX_LAUNCHER_TITLE,
                "Could not find the app executable. Build or install it first.",
            )


def run_app() -> None:
    app = LauncherApp()
    app.mainloop()


def main() -> int:
    install_crash_logging("NDEX Launcher")
    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
