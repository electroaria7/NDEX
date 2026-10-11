from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from ndex_common.branding import NDEX_LAUNCHER_TITLE
from ndex_common import i18n
from ndex_common.crashlog import install_crash_logging
from ndex_common.i18n import _
from ndex_common.launch import launch_app
from ndex_common.report_dialog import open_job_reports
from ndex_common.settings import settings_path
from ndex_common.theme import (
    APP_BG,
    add_tooltip,
    apply_tk_theme,
    apply_window_icon,
    build_app_header,
)

from ndex_launcher.state import StepState, gather_workflow_state

# Four cards need room for the headings as well as their bodies. Larger fonts
# can raise this threshold further through the measured heading widths.
COMPACT_LAYOUT_WIDTH = 1000
def tagline() -> str:
    return _("Start with 01 Backup. Each step hands its folder to the next.")


def uses_compact_card_layout(width: int, required_width: int = COMPACT_LAYOUT_WIDTH) -> bool:
    return width < required_width


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
        self._card_headings: dict[str, tuple[ttk.Label, ttk.Label]] = {}
        apply_tk_theme(self)
        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        header = build_app_header(
            self,
            title=NDEX_LAUNCHER_TITLE,
            tagline=tagline(),
            holder=self.brand_images,
            compact=True,
        )
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header.grid(row=0, column=0, sticky="ew")

        viewport = ttk.Frame(self)
        viewport.grid(row=1, column=0, sticky="nsew")
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(viewport, background=APP_BG, highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar = ttk.Scrollbar(viewport, orient=tk.VERTICAL, command=self._canvas.yview)
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._body = ttk.Frame(self._canvas, padding=(16, 4, 16, 8))
        self._body_window = self._canvas.create_window(0, 0, anchor="nw", window=self._body)
        self._canvas.bind("<Configure>", self._resize_viewport)
        self._body.bind("<Configure>", self._update_scroll_region)
        # Shorter refreshed cards can move the canvas window fully above the
        # old scroll position, where Tk unmaps it instead of sending Configure.
        self._body.bind("<Unmap>", self._update_scroll_region)
        self.bind("<MouseWheel>", self._scroll_cards, add="+")
        self.bind("<FocusIn>", self._reveal_focused_control, add="+")

        self._cards = {}
        self._arrows = []
        for step in gather_workflow_state():
            self._cards[step.key] = ttk.Frame(self._body, padding=14, style="Card.TFrame")
        self.bind("<Configure>", self._on_window_configure, add="+")
        self._apply_card_layout(self.winfo_width())

        footer = ttk.Frame(self, padding=(20, 4, 20, 12), style="Footer.TFrame")
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(2, weight=1)
        ttk.Button(footer, text=_("Refresh Status"), command=self.refresh_status).grid(row=0, column=0)
        ttk.Button(footer, text=_("Job Results..."), command=self.open_job_results).grid(
            row=0, column=1, padx=(8, 0)
        )
        self._language_note = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self._language_note, style="Small.Muted.TLabel").grid(
            row=0, column=2, sticky="e", padx=(12, 12)
        )
        self._build_language_selector(footer)
        # The path stays available, just out of the way: hover for the full text.
        settings_label = ttk.Label(footer, text=_("Settings file"), style="Small.Muted.TLabel", cursor="hand2")
        settings_label.grid(row=0, column=5, sticky="e", padx=(16, 0))
        add_tooltip(settings_label, lambda: _("Shared settings: {path}").format(path=settings_path()))

    def _language_choices(self) -> list[tuple[str, str]]:
        """``(setting value, label)`` pairs: System default first, then every language."""
        return [(i18n.SYSTEM, _("System default"))] + i18n.available_languages()

    def _build_language_selector(self, footer: ttk.Frame) -> None:
        choices = self._language_choices()
        self._language_codes = [code for code, _label in choices]
        ttk.Label(footer, text=_("Language"), style="Small.Muted.TLabel").grid(row=0, column=3, sticky="e")
        combo = ttk.Combobox(
            footer, values=[label for _code, label in choices], state="readonly", width=16
        )
        saved = i18n.configured_language()
        combo.current(self._language_codes.index(saved) if saved in self._language_codes else 0)
        combo.grid(row=0, column=4, sticky="e", padx=(6, 0))
        combo.bind("<<ComboboxSelected>>", self._on_language_selected)
        self.language_combo = combo

    def _on_language_selected(self, _event: tk.Event | None = None) -> None:
        code = self._language_codes[self.language_combo.current()]
        try:
            i18n.set_language(code)
        except OSError as exc:
            messagebox.showerror(NDEX_LAUNCHER_TITLE, _("Could not save the language: {error}").format(error=exc))
            return
        self._language_note.set(_("Restart NDEX apps to apply the language."))

    def _resize_viewport(self, event: tk.Event) -> None:
        self._fit_body(event.width, event.height)

    def _update_scroll_region(self, event: tk.Event) -> None:
        self._fit_body(self._canvas.winfo_width(), self._canvas.winfo_height())

    def _fit_body(self, width: int, height: int) -> None:
        """Keep cards at their content height, with scrolling when they overflow."""
        needed = self._body.winfo_reqheight()
        self._canvas.itemconfigure(self._body_window, width=width)
        self._canvas.configure(scrollregion=(0, 0, width, max(needed, height)))
        self._set_scrollbar_visible(needed > height > 1)

    def _set_scrollbar_visible(self, visible: bool) -> None:
        mapped = bool(self._scrollbar.winfo_manager())
        if visible and not mapped:
            self._scrollbar.grid()
        elif not visible and mapped:
            self._scrollbar.grid_remove()

    def _scroll_cards(self, event: tk.Event) -> None:
        if self._body.winfo_reqheight() > self._canvas.winfo_height():
            self._canvas.yview_scroll(-int(event.delta / 120), "units")

    def _reveal_focused_control(self, event: tk.Event) -> None:
        widget = event.widget
        if not str(widget).startswith(str(self._body) + "."):
            return
        top = widget.winfo_rooty() - self._body.winfo_rooty()
        bottom = top + widget.winfo_height()
        visible_top = self._canvas.canvasy(0)
        height = self._canvas.winfo_height()
        bounds = tuple(float(value) for value in self._canvas.cget("scrollregion").split())
        total = max(1, bounds[3] - bounds[1]) if bounds else 1
        if top < visible_top:
            self._canvas.yview_moveto(top / total)
        elif bottom > visible_top + height:
            self._canvas.yview_moveto((bottom - height) / total)

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        self._apply_card_layout(event.width)

    def _apply_card_layout(self, width: int) -> None:
        compact = uses_compact_card_layout(width, self._required_row_width())
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
            return

        for index, card in enumerate(cards):
            card.grid(row=0, column=index * 2, sticky="nsew", padx=(0, 0))
            self._body.columnconfigure(index * 2, weight=1, uniform="steps")
            if index < len(cards) - 1:
                arrow = ttk.Label(self._body, text="→", style="Arrow.TLabel")
                arrow.grid(row=0, column=index * 2 + 1, padx=2)
                self._arrows.append(arrow)

    def _required_row_width(self) -> int:
        style = ttk.Style(self)
        number_font = tkfont.Font(self, font=style.lookup("StepNumber.TLabel", "font"))
        title_font = tkfont.Font(self, font=style.lookup("CardTitle.TLabel", "font"))
        heading_width = max(
            (number_font.measure(str(number.cget("text"))) + title_font.measure(str(title.cget("text"))) + 6
             for number, title in self._card_headings.values()),
            default=0,
        )
        # Card padding, a little breathing room, the body margin, and arrows.
        arrow_font = tkfont.Font(self, font=style.lookup("Arrow.TLabel", "font"))
        return max(COMPACT_LAYOUT_WIDTH, (heading_width + 40) * 4 + 32 + (arrow_font.measure("→") + 8) * 3)

    def refresh_status(self) -> None:
        steps = gather_workflow_state()
        for step in steps:
            if step.key not in self._cards:
                self._cards[step.key] = ttk.Frame(self._body, padding=14, style="Card.TFrame")
                self._compact_layout = None
                self._apply_card_layout(self.winfo_width())
            self._render_card(step)
        self._apply_card_layout(self.winfo_width())

    def _render_card(self, step: StepState) -> None:
        card = self._cards[step.key]
        card.bind("<Configure>", self._wrap_card_text)
        for child in card.winfo_children():
            child.destroy()

        heading = ttk.Frame(card, style="CardInner.TFrame")
        heading.pack(anchor="w", fill=tk.X)
        number = ttk.Label(
            heading,
            text=step.number or step.title.split(".", 1)[0],
            style="StepNumber.TLabel",
        )
        number.pack(side=tk.LEFT)
        title = ttk.Label(
            heading,
            text=step.short_title or step.title,
            style="CardTitle.TLabel",
        )
        title.pack(side=tk.LEFT, padx=(6, 0), pady=(5, 0))
        self._card_headings[step.key] = (number, title)
        ttk.Label(card, text=step.description, style="Card.TLabel", wraplength=160, justify="left").pack(
            anchor="w", pady=(6, 8)
        )
        status = ttk.Label(card, text=step.status_text, style="CardMuted.TLabel", wraplength=160, justify="left")
        status.pack(anchor="w", pady=(0, 2))
        if step.status_tooltip:
            add_tooltip(status, step.status_tooltip)
        problem = step.result_is_problem
        ttk.Label(
            card,
            text=f"⚠ {step.result_text}" if problem else step.result_text,
            style="CardDanger.TLabel" if problem else "CardMuted.TLabel",
            wraplength=160,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        # Buttons sit at the bottom so the four cards line up in the 1x4 row.
        buttons = ttk.Frame(card, style="CardInner.TFrame")
        buttons.pack(side=tk.BOTTOM, fill=tk.X, anchor="s")
        continue_label = _("Continue") if step.has_session else _("Open")
        ttk.Button(
            buttons,
            text=continue_label,
            style="Accent.TButton",
            command=lambda s=step: self._launch(s.key, s.launch_args),
        ).pack(anchor="w", fill=tk.X)
        if step.has_session:
            ttk.Button(
                buttons,
                text=_("Start Fresh"),
                command=lambda s=step: self._launch(s.key, ["--open"]),
            ).pack(anchor="w", fill=tk.X, pady=(6, 0))

    def _wrap_card_text(self, event: tk.Event) -> None:
        for child in event.widget.winfo_children():
            if isinstance(child, ttk.Label):
                child.configure(wraplength=max(80, event.width - 36))

    def open_job_results(self) -> None:
        """Show what every app's recent jobs copied, skipped, or failed on."""
        open_job_reports(self, title=NDEX_LAUNCHER_TITLE, open_in_app=self.retry_in_app)

    def retry_in_app(self, report) -> None:
        """Open the app that ran this job, at this job, so it can retry.

        The Launcher owns no executor, so it never runs the files itself:
        the app opens its own Job Results and the user presses Retry there,
        with that app's settings in view.
        """
        self._launch(report.app, ["--open", "--retry", str(report.manifest_path)])

    def _launch(self, app_key: str, args: list[str]) -> None:
        try:
            launched = launch_app(app_key, args)
        except OSError as exc:
            messagebox.showerror(NDEX_LAUNCHER_TITLE, _("Launch failed: {error}").format(error=exc))
            return
        if not launched:
            messagebox.showerror(
                NDEX_LAUNCHER_TITLE,
                _("Could not find the app executable. Build or install it first."),
            )


def run_app() -> None:
    app = LauncherApp()
    app.mainloop()


def main() -> int:
    install_crash_logging("NDEX Launcher")
    i18n.init("launcher")
    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
