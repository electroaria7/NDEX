from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ndex_common.branding import (
    APP_ICON_32,
    APP_ICON_64,
    APP_WORDMARK_HEADER,
    NDEX_LAUNCHER_TITLE,
    get_branding_asset_path,
)
from ndex_common.launch import launch_app
from ndex_common.settings import settings_path

from ndex_launcher.state import StepState, gather_workflow_state

APP_BG = "#f5f7fb"
CARD_BG = "#ffffff"
TEXT_PRIMARY = "#18202f"
TEXT_MUTED = "#64748b"
ACCENT = "#2563eb"
COMPACT_LAYOUT_WIDTH = 1100


def uses_compact_card_layout(width: int) -> bool:
    return width < COMPACT_LAYOUT_WIDTH


class LauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(NDEX_LAUNCHER_TITLE)
        self.geometry("980x560")
        self.minsize(880, 500)
        self.resizable(True, True)
        self.brand_images: list[tk.PhotoImage] = []
        self._apply_window_branding()

        self.status_labels: dict[str, tk.StringVar] = {}
        self._cards: dict[str, ttk.Frame] = {}
        self._arrows: list[ttk.Label] = []
        self._compact_layout: bool | None = None
        self._configure_style()
        self._build_ui()
        self.refresh_status()

    def _apply_window_branding(self) -> None:
        try:
            icons = []
            for relative in (APP_ICON_32, APP_ICON_64):
                path = get_branding_asset_path(relative)
                if path.exists():
                    image = tk.PhotoImage(file=str(path))
                    self.brand_images.append(image)
                    icons.append(image)
            if icons:
                self.iconphoto(True, *icons)
        except tk.TclError:
            pass

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(bg=APP_BG)
        style.configure("TFrame", background=APP_BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("TLabel", background=APP_BG, foreground=TEXT_PRIMARY, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=APP_BG, foreground=TEXT_PRIMARY, font=("Segoe UI", 16, "bold"))
        style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=("Segoe UI", 9))
        style.configure("CardTitle.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=("Segoe UI", 11, "bold"))
        style.configure("CardMuted.TLabel", background=CARD_BG, foreground=TEXT_MUTED, font=("Segoe UI", 8))
        style.configure("Arrow.TLabel", background=APP_BG, foreground=ACCENT, font=("Segoe UI", 18, "bold"))
        style.configure("TButton", padding=(10, 6), font=("Segoe UI", 9))

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(20, 16, 20, 4))
        header.pack(fill=tk.X)
        wordmark_path = get_branding_asset_path(APP_WORDMARK_HEADER)
        if wordmark_path.exists():
            try:
                image = tk.PhotoImage(file=str(wordmark_path))
                self.brand_images.append(image)
                ttk.Label(header, image=image).pack(side=tk.LEFT)
            except tk.TclError:
                ttk.Label(header, text=NDEX_LAUNCHER_TITLE, style="Title.TLabel").pack(side=tk.LEFT)
        else:
            ttk.Label(header, text=NDEX_LAUNCHER_TITLE, style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="Photo workflow: backup, select, extract, frame",
        ).pack(side=tk.LEFT, padx=(14, 0), pady=(6, 0))

        self._body = ttk.Frame(self, padding=20)
        self._body.pack(fill=tk.BOTH, expand=True)

        self._cards = {}
        self._arrows = []
        for step in gather_workflow_state():
            self._cards[step.key] = ttk.Frame(self._body, padding=16, style="Card.TFrame")
        self.bind("<Configure>", self._on_window_configure, add="+")
        self._apply_card_layout(self.winfo_width())

        footer = ttk.Frame(self, padding=(20, 0, 20, 14))
        footer.pack(fill=tk.X)
        ttk.Button(footer, text="Refresh Status", command=self.refresh_status).pack(side=tk.LEFT)
        ttk.Label(
            footer,
            text=f"Shared settings: {settings_path()}",
            foreground=TEXT_MUTED,
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
            card.grid(row=0, column=index * 2, sticky="nsew")
            self._body.columnconfigure(index * 2, weight=1, uniform="steps")
            if index < len(cards) - 1:
                arrow = ttk.Label(self._body, text="→", style="Arrow.TLabel")
                arrow.grid(row=0, column=index * 2 + 1, padx=6)
                self._arrows.append(arrow)
        self._body.rowconfigure(0, weight=1)

    def refresh_status(self) -> None:
        steps = gather_workflow_state()
        for step in steps:
            if step.key not in self._cards:
                self._cards[step.key] = ttk.Frame(self._body, padding=16, style="Card.TFrame")
                self._compact_layout = None
                self._apply_card_layout(self.winfo_width())
            self._render_card(step)

    def _render_card(self, step: StepState) -> None:
        card = self._cards[step.key]
        for child in card.winfo_children():
            child.destroy()

        ttk.Label(card, text=step.title, style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(card, text=step.description, style="Card.TLabel", wraplength=250, justify="left").pack(
            anchor="w", pady=(6, 10)
        )
        ttk.Label(card, text=step.status_text, style="CardMuted.TLabel", wraplength=250, justify="left").pack(
            anchor="w", pady=(0, 12)
        )

        continue_label = "Continue" if step.has_session and step.key != "ndex_one" else "Open"
        ttk.Button(
            card,
            text=continue_label,
            command=lambda s=step: self._launch(s.key, s.launch_args),
        ).pack(anchor="w", fill=tk.X)
        if step.key != "ndex_one" and step.has_session:
            ttk.Button(
                card,
                text="Open Empty",
                command=lambda s=step: self._launch(s.key, ["--open"]),
            ).pack(anchor="w", fill=tk.X, pady=(6, 0))

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
    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
