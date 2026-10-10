"""Shared NDEX visual language for Tk and Qt apps.

Keep chrome light and consistent across the suite. Photo preview wells stay
dark on purpose so images read clearly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from ndex_common.branding import (
    APP_ICON_16, APP_ICON_24, APP_ICON_32, APP_ICON_48, APP_ICON_64,
    APP_WORDMARK_HEADER, get_branding_asset_path,
)

# Canvas and surfaces
APP_BG = "#F3F5F9"
CARD_BG = "#FFFFFF"
SURFACE_SUNKEN = "#E8EDF4"
BORDER = "#D5DCE6"
BORDER_STRONG = "#C3CDDB"
# Secondary buttons: a tinted face and a firmer edge so they read as buttons
# on both the app canvas and white cards.
BUTTON_BG = "#EDF1F7"
BUTTON_HOVER_BG = "#DCE5F2"
BUTTON_BORDER = "#9AA9BF"

# Text
TEXT_PRIMARY = "#1B2433"
TEXT_MUTED = "#5B6B80"
TEXT_FAINT = "#8A97A8"

# Accent and status
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#E8F0FE"
ACCENT_TEXT = "#FFFFFF"
DANGER = "#DC2626"
SUCCESS = "#047857"
STAR = "#D49B10"
SELECTION_BG = "#DBEAFE"

# Preview wells (photo surfaces, not chrome)
PREVIEW_WELL = "#1C2128"
PREVIEW_WELL_TEXT = "#AEB4BD"

FONT_FAMILY = "Segoe UI"
FONT_SYMBOL = "Segoe UI Symbol"
FONT_SIZE = 9
FONT_TITLE_SIZE = 18
FONT_SECTION_SIZE = 11

# Layout
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 20
HEADER_PAD = (20, 12, 20, 10)
HEADER_PAD_COMPACT = (20, 8, 20, 8)
BODY_PAD = 16

_TK_THEME_APPLIED = "ndex.tk.theme.applied"
_QT_THEME_MARKER = "/* NDEX-THEME */"


def load_brand_image(root: tk.Misc, relative_path: Path, holder: list[tk.PhotoImage]) -> tk.PhotoImage | None:
    path = get_branding_asset_path(relative_path)
    if not path.exists():
        return None
    try:
        image = tk.PhotoImage(master=root, file=str(path))
    except tk.TclError:
        return None
    holder.append(image)
    return image


def apply_window_icon(root: tk.Tk, holder: list[tk.PhotoImage]) -> None:
    icons = [
        icon for path in (APP_ICON_16, APP_ICON_24, APP_ICON_32, APP_ICON_48, APP_ICON_64)
        if (icon := load_brand_image(root, path, holder)) is not None
    ]
    if icons:
        try:
            root.iconphoto(True, *icons)
        except tk.TclError:
            pass


def build_app_header(
    parent: tk.Misc,
    *,
    title: str,
    tagline: str,
    holder: list[tk.PhotoImage],
    compact: bool = False,
) -> ttk.Frame:
    """A small wordmark beside the app name, with the task description below."""
    header = ttk.Frame(parent, padding=HEADER_PAD_COMPACT if compact else HEADER_PAD, style="Header.TFrame")
    header.columnconfigure(1, weight=1)
    wordmark = load_brand_image(parent, APP_WORDMARK_HEADER, holder)
    if wordmark is not None:
        wordmark = wordmark.subsample(3, 3) if compact else wordmark.zoom(2, 2).subsample(5, 5)
        holder.append(wordmark)
        ttk.Label(header, image=wordmark, style="Header.TLabel").grid(row=0, column=0, padx=(0, 14))
    title_label = ttk.Label(header, text=title, style="Title.TLabel")
    title_label.grid(row=0, column=1, sticky="w")
    description = ttk.Label(header, text=tagline, style="Tagline.TLabel", justify="left", wraplength=600)
    description.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))

    def wrap_description(event: tk.Event) -> None:
        description.configure(wraplength=max(120, event.width))

    description.bind("<Configure>", wrap_description, add="+")
    return header


class ScrollableFrame(ttk.Frame):
    """A vertically scrolling form with keyboard focus and local wheel support.

    Add widgets to ``content``. The surrounding frame can reserve space for
    actions outside the scroll area, even when display scaling makes a form tall.
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        style: str = "TFrame",
        content_style: str = "TFrame",
        background: str = APP_BG,
    ) -> None:
        super().__init__(parent, style=style)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background=background, highlightthickness=0, width=1, height=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = ttk.Frame(self.canvas, style=content_style)
        self._window = self.canvas.create_window(0, 0, anchor="nw", window=self.content)
        self.canvas.bind("<Configure>", self._fit_content)
        self.content.bind("<Configure>", self._fit_content)
        # If a scrolled form shrinks above the viewport, Tk unmaps the canvas
        # window without applying its new requested height. Refit on Unmap as
        # well so the scrollregion shrinks and brings the remaining form back.
        self.content.bind("<Unmap>", self._fit_content)
        self._toplevel = self.winfo_toplevel()
        self._bindings = {
            "<MouseWheel>": self._toplevel.bind("<MouseWheel>", self._scroll, add="+"),
            "<FocusIn>": self._toplevel.bind("<FocusIn>", self.reveal_focused_control, add="+"),
        }
        self.bind("<Destroy>", self._cleanup_bindings, add="+")

    def _fit_content(self, _event: tk.Event | None = None) -> None:
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        needed = self.content.winfo_reqheight()
        self.canvas.itemconfigure(self._window, width=width)
        self.canvas.configure(scrollregion=(0, 0, width, max(needed, height)))
        if needed > height > 1:
            self.scrollbar.grid()
        else:
            self.scrollbar.grid_remove()

    def _contains(self, widget: tk.Misc) -> bool:
        return str(widget).startswith(str(self.content) + ".") or widget is self.content or widget is self.canvas

    def _scroll(self, event: tk.Event) -> str | None:
        if not self._contains(event.widget) or self.content.winfo_reqheight() <= self.canvas.winfo_height():
            return None
        if event.widget.winfo_class() in {"Text", "Treeview", "TCombobox", "TSpinbox"}:
            return None
        if event.delta:
            direction = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(direction * max(1, abs(int(event.delta / 120))), "units")
            return "break"
        return None

    def reveal_focused_control(self, event: tk.Event) -> None:
        widget = event.widget
        if not self._contains(widget):
            return
        top = widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = top + widget.winfo_height()
        visible_top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        # A canvas window can still report its previous height while a resize
        # is pending; yview fractions always refer to the current scrollregion.
        bounds = tuple(float(value) for value in self.canvas.cget("scrollregion").split())
        total = max(1, bounds[3] - bounds[1]) if bounds else 1
        if top < visible_top:
            self.canvas.yview_moveto(top / total)
        elif bottom > visible_top + height:
            self.canvas.yview_moveto((bottom - height) / total)

    def _cleanup_bindings(self, event: tk.Event) -> None:
        if event.widget is self:
            for sequence, binding in self._bindings.items():
                if binding:
                    self._toplevel.unbind(sequence, binding)


class Tooltip:
    """A small hover tooltip. ``text`` may be a string or a callable returning one."""

    DELAY_MS = 450

    def __init__(self, widget: tk.Misc, text: "str | Callable[[], str]") -> None:
        self.widget = widget
        self.text = text
        self._tip: tk.Toplevel | None = None
        self._after: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def current_text(self) -> str:
        return self.text() if callable(self.text) else str(self.text)

    def _schedule(self, _event: object = None) -> None:
        self._cancel()
        try:
            self._after = self.widget.after(self.DELAY_MS, self._show)
        except tk.TclError:
            self._after = None

    def _cancel(self) -> None:
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self) -> None:
        self._after = None
        text = self.current_text()
        if not text or self._tip is not None:
            return
        try:
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tip,
                text=text,
                justify="left",
                wraplength=520,
                background=TEXT_PRIMARY,
                foreground=CARD_BG,
                font=(FONT_FAMILY, FONT_SIZE),
                padx=8,
                pady=4,
            ).pack()
        except tk.TclError:
            return
        self._tip = tip

    def _hide(self, _event: object = None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def add_tooltip(widget: tk.Misc, text: "str | Callable[[], str]") -> Tooltip:
    return Tooltip(widget, text)


def style_text_widget(widget: tk.Text, *, card: bool = True) -> None:
    background = CARD_BG if card else APP_BG
    widget.configure(
        background=background,
        foreground=TEXT_PRIMARY,
        insertbackground=TEXT_PRIMARY,
        selectbackground=SELECTION_BG,
        selectforeground=TEXT_PRIMARY,
        relief=tk.FLAT,
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
        font=(FONT_FAMILY, FONT_SIZE),
        padx=10,
        pady=8,
    )


def apply_tk_theme(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=APP_BG)
    font_ui = (FONT_FAMILY, FONT_SIZE)
    font_ui_bold = (FONT_FAMILY, FONT_SIZE, "bold")
    font_title = (FONT_FAMILY, FONT_TITLE_SIZE, "bold")
    font_section = (FONT_FAMILY, FONT_SECTION_SIZE, "bold")
    font_card_title = (FONT_FAMILY, 12, "bold")
    font_step = (FONT_FAMILY, 18, "bold")
    font_tagline = (FONT_FAMILY, FONT_SIZE)

    style.configure("TFrame", background=APP_BG)
    style.configure("Header.TFrame", background=APP_BG)
    style.configure("Card.TFrame", background=CARD_BG, borderwidth=1, relief="solid", bordercolor=BORDER)
    style.configure("CardInner.TFrame", background=CARD_BG)
    style.configure("Toolbar.TFrame", background=CARD_BG, borderwidth=1, relief="solid", bordercolor=BORDER)
    style.configure("Footer.TFrame", background=APP_BG)

    style.configure("TLabel", background=APP_BG, foreground=TEXT_PRIMARY, font=font_ui)
    style.configure("Header.TLabel", background=APP_BG, foreground=TEXT_PRIMARY)
    style.configure("Muted.TLabel", background=APP_BG, foreground=TEXT_MUTED, font=font_ui)
    style.configure("Faint.TLabel", background=APP_BG, foreground=TEXT_FAINT, font=font_ui)
    style.configure("Title.TLabel", background=APP_BG, foreground=TEXT_PRIMARY, font=font_title)
    style.configure("Tagline.TLabel", background=APP_BG, foreground=TEXT_MUTED, font=font_tagline)
    style.configure("Section.TLabel", background=APP_BG, foreground=TEXT_PRIMARY, font=font_section)
    style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=font_ui)
    style.configure("CardMuted.TLabel", background=CARD_BG, foreground=TEXT_MUTED, font=font_ui)
    style.configure("CardFaint.TLabel", background=CARD_BG, foreground=TEXT_FAINT, font=font_ui)
    style.configure("CardTitle.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=font_card_title)
    style.configure("CardSection.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=font_section)
    style.configure("Toolbar.TLabel", background=CARD_BG, foreground=TEXT_MUTED, font=font_ui_bold)
    style.configure("CardDanger.TLabel", background=CARD_BG, foreground=DANGER, font=font_ui)
    style.configure("Danger.TLabel", background=APP_BG, foreground=DANGER, font=font_ui)
    style.configure("Small.Muted.TLabel", background=APP_BG, foreground=TEXT_MUTED, font=(FONT_FAMILY, FONT_SIZE - 1))
    style.configure("StepNumber.TLabel", background=CARD_BG, foreground=ACCENT, font=font_step)
    style.configure("Arrow.TLabel", background=APP_BG, foreground=BORDER_STRONG, font=(FONT_FAMILY, 16))

    style.configure(
        "TButton",
        background=BUTTON_BG,
        foreground=TEXT_PRIMARY,
        bordercolor=BUTTON_BORDER,
        darkcolor=BUTTON_BORDER,
        lightcolor=BUTTON_BG,
        padding=(12, 7),
        font=font_ui,
        relief="flat",
        borderwidth=1,
    )
    style.map(
        "TButton",
        background=[("pressed", BUTTON_BORDER), ("active", BUTTON_HOVER_BG), ("disabled", APP_BG)],
        foreground=[("disabled", TEXT_FAINT)],
        bordercolor=[("active", ACCENT), ("disabled", BORDER)],
        lightcolor=[("pressed", BUTTON_BORDER), ("active", BUTTON_HOVER_BG), ("disabled", APP_BG)],
        darkcolor=[("active", ACCENT), ("disabled", BORDER)],
    )
    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground=ACCENT_TEXT,
        bordercolor=ACCENT,
        darkcolor=ACCENT,
        lightcolor=ACCENT,
        padding=(12, 7),
        font=font_ui_bold,
        relief="flat",
        borderwidth=1,
    )
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_HOVER), ("disabled", "#93C5FD")],
        foreground=[("disabled", ACCENT_TEXT)],
        bordercolor=[("active", ACCENT_HOVER), ("disabled", "#93C5FD")],
    )

    style.configure("TCheckbutton", background=APP_BG, foreground=TEXT_PRIMARY, font=font_ui, padding=(0, 2))
    style.map("TCheckbutton", background=[("active", APP_BG)], foreground=[("disabled", TEXT_FAINT)])
    style.configure("Card.TCheckbutton", background=CARD_BG, foreground=TEXT_PRIMARY, font=font_ui, padding=(0, 2))
    style.map("Card.TCheckbutton", background=[("active", CARD_BG)], foreground=[("disabled", TEXT_FAINT)])

    style.configure(
        "TEntry",
        fieldbackground=CARD_BG,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(8, 6),
        insertcolor=TEXT_PRIMARY,
    )
    style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])

    style.configure(
        "TCombobox",
        fieldbackground=CARD_BG,
        background=CARD_BG,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER,
        arrowcolor=TEXT_MUTED,
        padding=(6, 5),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", CARD_BG)],
        foreground=[("readonly", TEXT_PRIMARY)],
        bordercolor=[("focus", ACCENT)],
    )

    style.configure(
        "TSpinbox",
        fieldbackground=CARD_BG,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER,
        arrowcolor=TEXT_MUTED,
        padding=(6, 4),
    )

    style.configure(
        "TLabelframe",
        background=CARD_BG,
        bordercolor=BORDER,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "TLabelframe.Label",
        background=CARD_BG,
        foreground=TEXT_MUTED,
        font=font_ui_bold,
    )

    style.configure(
        "TProgressbar",
        troughcolor=SURFACE_SUNKEN,
        background=ACCENT,
        bordercolor=BORDER,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        thickness=8,
    )

    style.configure(
        "Treeview",
        rowheight=30,
        background=CARD_BG,
        fieldbackground=CARD_BG,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        borderwidth=0,
        relief="flat",
        font=font_ui,
    )
    style.configure(
        "Treeview.Heading",
        background=SURFACE_SUNKEN,
        foreground=TEXT_MUTED,
        bordercolor=BORDER,
        relief="flat",
        borderwidth=0,
        font=font_ui_bold,
        padding=(8, 6),
    )
    style.map(
        "Treeview",
        background=[("selected", SELECTION_BG)],
        foreground=[("selected", TEXT_PRIMARY)],
    )
    style.map("Treeview.Heading", background=[("active", BORDER)])

    style.configure("TPanedwindow", background=APP_BG)
    style.configure("TScrollbar", troughcolor=APP_BG, background=BORDER_STRONG, bordercolor=APP_BG, arrowcolor=TEXT_MUTED)
    style.map("TScrollbar", background=[("active", TEXT_FAINT)])

    style.configure("TSeparator", background=BORDER)

    setattr(root, _TK_THEME_APPLIED, True)
    return style


def qt_stylesheet() -> str:
    return f"""
{_QT_THEME_MARKER}
QWidget {{
    color: {TEXT_PRIMARY};
    font-family: "{FONT_FAMILY}";
    font-size: {FONT_SIZE}pt;
}}
QMainWindow, QDialog, QSplitter {{
    background-color: {APP_BG};
}}
QToolBar {{
    background: {CARD_BG};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 12px;
    spacing: 8px;
}}
QToolBar QLabel {{
    background: transparent;
    color: {TEXT_MUTED};
    font-weight: 600;
    padding-left: 4px;
}}
QStatusBar {{
    background: {CARD_BG};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
}}
QPushButton {{
    background: {CARD_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 22px;
}}
QPushButton:hover {{
    background: {SURFACE_SUNKEN};
    border-color: {BORDER_STRONG};
}}
QPushButton:pressed {{
    background: {BORDER};
}}
QPushButton:disabled {{
    color: {TEXT_FAINT};
    background: {SURFACE_SUNKEN};
}}
QPushButton#primaryButton {{
    background: {ACCENT};
    color: {ACCENT_TEXT};
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#primaryButton:disabled {{
    background: #93C5FD;
    border-color: #93C5FD;
    color: {ACCENT_TEXT};
}}
QPushButton#compactButton {{
    padding: 4px 8px;
    min-height: 22px;
}}
QPushButton#colorSwatch {{
    padding: 0px;
    margin: 0px;
    min-width: 30px;
    min-height: 30px;
    border-radius: 6px;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {CARD_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
    selection-background-color: {SELECTION_BG};
    selection-color: {TEXT_PRIMARY};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QListWidget {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 6px;
    border-radius: 6px;
    color: {TEXT_PRIMARY};
}}
QListWidget::item:selected {{
    background: {ACCENT_SOFT};
    color: {TEXT_PRIMARY};
}}
QProgressBar {{
    background: {SURFACE_SUNKEN};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    color: {TEXT_PRIMARY};
    height: 18px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 5px;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -6px 0;
    background: {ACCENT};
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_HOVER};
}}
QLabel {{
    background: transparent;
    color: {TEXT_PRIMARY};
}}
QLabel#sectionLabel {{
    font-weight: 600;
    font-size: 11pt;
    color: {TEXT_PRIMARY};
    padding-bottom: 2px;
}}
QLabel#mutedLabel {{
    color: {TEXT_MUTED};
}}
QWidget#previewWell {{
    background-color: {PREVIEW_WELL};
}}
QWidget#sidePanel {{
    background: {CARD_BG};
    border-left: 1px solid {BORDER};
}}
QWidget#thumbPanel {{
    background: {CARD_BG};
    border-right: 1px solid {BORDER};
}}
QWidget#footerBar {{
    background: {CARD_BG};
    border-top: 1px solid {BORDER};
}}
QGroupBox {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_MUTED};
}}
QCheckBox, QRadioButton {{
    background: transparent;
    spacing: 8px;
}}
QScrollBar:vertical {{
    background: {APP_BG};
    width: 10px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QSplitter::handle {{
    background: {BORDER};
    width: 1px;
}}
QColorDialog, QFileDialog {{
    background: {APP_BG};
}}
"""


def apply_qt_theme(_widget: Any | None = None) -> None:
    """Apply Fusion + the NDEX stylesheet to the current QApplication."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return

    app = QApplication.instance()
    if app is None:
        return
    try:
        if app.style().objectName().lower() != "fusion":
            app.setStyle("Fusion")
    except Exception:
        pass
    if _QT_THEME_MARKER not in (app.styleSheet() or ""):
        app.setStyleSheet(qt_stylesheet())
