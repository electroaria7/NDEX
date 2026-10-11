from __future__ import annotations

import logging
import os
import queue
import threading
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from PIL import Image, ImageOps, ImageTk

from src.branding import NDEX_IMAGE_MANAGER_TITLE

from ..core.models import (
    ExportOptions,
    ImageRecord,
    MarkChange,
    Shot,
    UndoStack,
    build_shots,
    shot_matches,
    sort_records,
    sort_shots,
)
from ..services.backup import BackupService
from ..services.catalog import Catalog
from ..services.exporter import ExportService
from ..services.scanner import ImageScanner, ScanCancelled
from ..services.xmp_export import XmpExportService

from ndex_common.launch import launch_app
from ndex_common.settings import get_section, update_section
from ndex_common.theme import (
    APP_BG,
    CARD_BG,
    STAR,
    TEXT_MUTED,
    TEXT_PRIMARY,
    Tooltip,
    apply_tk_theme,
    apply_window_icon,
    build_app_header,
    style_text_widget,
)

SETTINGS_SECTION = "image_manager"
log = logging.getLogger(__name__)
UNDO_LIMIT = 100

STAR_FILLED = "\u2605"
STAR_EMPTY = "\u2606"
SORT_ASC = "\u2191"
SORT_DESC = "\u2193"
PREVIEW_BACKGROUNDS = {
    "50% Gray": "#808080",
    "Dark Gray": "#1f2933",
    "Light Gray": "#d1d5db",
}
TREE_COLUMNS = {
    "state": {"label": "", "sort_key": "pick_status", "width": 24, "minwidth": 24, "stretch": False,
              "anchor": "center", "indicator": False},
    "name": {"label": "File", "sort_key": "file_name", "width": 120, "minwidth": 84, "stretch": True},
    "type": {"label": "Type", "sort_key": "media_type", "width": 42, "minwidth": 42, "stretch": False},
    "pick": {"label": "Pick", "sort_key": "pick_status", "width": 48, "minwidth": 48, "stretch": False},
    "rating": {"label": "\u2605", "sort_key": "rating", "width": 64, "minwidth": 64, "stretch": False},
    "date": {"label": "Date", "sort_key": "capture_datetime", "width": 64, "minwidth": 64, "stretch": False},
}
# Tints are a second cue only; the first column carries the pick glyph.
PICK_TINTS = {"Pick": "#d2efd5", "Maybe": "#ffeeb0", "Reject": "#f8cfcf"}
PICK_BADGES = {
    "Pick": ("\u2713 PICK", "#15803d"),
    "Maybe": ("? MAYBE", "#b45309"),
    "Reject": ("\u2715 REJECT", "#b91c1c"),
    "Unrated": ("UNRATED", "#4b5563"),
}
FILE_FILTER_LABELS = (
    ("all", "All files"),
    ("paired", "Pairs (RAW+JPG)"),
    ("raw", "RAW only"),
    ("jpg", "JPG only"),
    ("raw_only", "Unpaired RAW"),
    ("jpg_only", "Unpaired JPG"),
    ("proxy_failed", "Preview failed"),
)
PICK_FILTER_LABELS = (
    ("all", "Any pick state"),
    ("Unrated", "Unrated"),
    ("Pick", "Pick"),
    ("Maybe", "Maybe"),
    ("Reject", "Reject"),
)
RATING_FILTER_LABELS = (
    ("0", "Any rating"),
    ("1", "1\u2605+"),
    ("3", "3\u2605+"),
    ("5", "5\u2605"),
)
# Sorting by these columns changes row order when a mark changes.
RESORT_KEYS = ("pick_status", "rating")
KIND_NAMES = {"scan": "Scan", "backup": "Backup", "export": "Export", "xmp": "XMP sidecars"}
PROGRESS_VERBS = {"scan": "Scanning", "backup": "Backing up", "export": "Exporting", "xmp": "Writing XMP"}
SHORTCUT_HINT = (
    "P Pick \u00b7 X Reject \u00b7 M Maybe \u00b7 U Clear \u00b7 0\u20135 Stars \u00b7 "
    "\u2190/\u2192 Move \u00b7 F Full screen \u00b7 Ctrl+Z Undo"
)
# Keys must stay editable/usable inside these widgets, so arrows are not hijacked.
TEXT_INPUT_CLASSES = frozenset({"TCombobox", "TEntry", "Entry", "TSpinbox", "Spinbox", "Text"})
MENU_HINTS = {
    "Backup Picked\u2026": "Copy every file of the picked shots (RAW and JPG) to a backup folder and verify the copies.",
    "Export Selected\u2026": "Copy the selected photos to a folder with a rename pattern.",
    "Write XMP Sidecars (for Lightroom/Evoto)": "Write .xmp files next to the photos with their star ratings and pick flags.",
    "Send Picks to Auto Selector": "Open the picked JPGs in Auto Selector.",
    "Send Picks to Frame": "Open the picked JPG/PNG/TIFF files in Frame.",
}


def label_for(options, value: str) -> str:
    return next((label for key, label in options if key == value), options[0][1])


def value_for(options, label: str) -> str:
    return next((key for key, text in options if text == label), options[0][0])


def plural(count: int, word: str, suffix: str = "s") -> str:
    return f"{count} {word}{'' if count == 1 else suffix}"


def record_matches_filters(record: ImageRecord, pick_filter: str, min_rating: int) -> bool:
    """Pick and rating part of the list filters (file-type filters never change on a mark)."""
    if pick_filter != "all" and record.pick_status != pick_filter:
        return False
    return record.rating >= min_rating


def progress_text(kind: str, index: int, total: int, name: str) -> str:
    return f"{PROGRESS_VERBS.get(kind, kind.title())} {index}/{total} \u2014 {name}"


def ready_status_text(total_files: int, shot_count: int) -> str:
    return f"Ready. {plural(total_files, 'file')} ({plural(shot_count, 'shot')})"


def selection_status_text(selected: int, shown: int) -> str:
    text = f"{selected} selected / {shown} shown"
    if selected > 1:
        text += f" \u2014 marks apply to all {selected}"
    return text


def position_text(index: int, total: int) -> str:
    return f"{index + 1} / {total}"


def preview_unavailable_text(record: ImageRecord) -> str:
    if record.media_type == "raw":
        if record.pair_status == "raw_jpg_pair":
            return "No embedded preview \u2014 view the JPG of this pair instead."
        return "No embedded preview in this RAW file."
    return "Preview unavailable"


def empty_state_kind(has_catalog: bool, scanning: bool, record_count: int, filters_active: bool) -> str | None:
    if scanning:
        return None
    if not has_catalog:
        return "start"
    if record_count:
        return None
    return "filtered" if filters_active else "empty"


def send_confirm_text(count: int, noun: str, target: str) -> str:
    return f"Send {plural(count, 'picked ' + noun)} to {target}?"


def no_jpg_text(count: int, sent: bool = False) -> str:
    """Picked shots that only have a RAW cannot be handed to JPG-only apps."""
    tail = "were not sent." if sent else "will not be sent."
    return f"{plural(count, 'picked shot')} {'has' if count == 1 else 'have'} no JPG and {tail}"


def file_counts_text(files) -> str:
    """'6 JPG + 6 RAW' for a list of file records."""
    files = list(files)
    jpg = sum(1 for record in files if record.media_type == "jpg")
    raw = sum(1 for record in files if record.media_type == "raw")
    other = len(files) - jpg - raw
    parts = [f"{jpg} JPG"] if jpg else []
    parts += [f"{raw} RAW"] if raw else []
    parts += [f"{other} other"] if other else []
    return " + ".join(parts)


def shot_files(shots) -> list[ImageRecord]:
    return [record for shot in shots for record in shot.records]


def backup_confirm_text(shots, destination) -> str:
    shots = list(shots)
    return (f"Back up {plural(len(shots), 'picked shot')} ({file_counts_text(shot_files(shots))}) "
            f"to:\n{destination}?")


PICK_LABELS = {"Pick": "Pick", "Maybe": "Maybe", "Reject": "Reject", "Unrated": "Clear pick"}
PICK_DONE = {"Pick": "Picked", "Maybe": "Marked Maybe", "Reject": "Rejected", "Unrated": "Cleared pick on"}


def mark_change_label(pick_status, rating, count: int, noun: str) -> str:
    """Edit-menu wording: 'Pick: Reject 12 shots' or 'Rating: 3\u2605 1 shot'."""
    if pick_status is not None:
        what = f"Pick: {PICK_LABELS.get(pick_status, pick_status)}"
    else:
        what = f"Rating: {f'{rating}{STAR_FILLED}' if rating else 'Clear'}"
    return f"{what} {plural(count, noun)}"


def mark_done_text(pick_status, rating, count: int, noun: str) -> str:
    if pick_status is not None:
        return f"{PICK_DONE.get(pick_status, pick_status)} {plural(count, noun)}"
    if rating:
        return f"Rated {plural(count, noun)} {rating}{STAR_FILLED}"
    return f"Cleared rating on {plural(count, noun)}"


def scan_stopped_text(listed: int, total: int) -> str:
    if total <= 0:
        return "Scan stopped before any files were listed. The previous catalog was kept."
    return f"Scan stopped \u2014 {listed} of {total} files listed. Rescan (F5) to finish."


def operation_summary_text(kind: str, summary, destination) -> str:
    where = f" to {destination}" if destination else ""
    if kind == "backup":
        done, noun = getattr(summary, "copied", 0), "file"
    elif kind == "export":
        done, noun = getattr(summary, "exported", 0), "file"
    else:
        done, noun = getattr(summary, "written", 0), "XMP sidecar"
        where = f" next to the photos in {destination}" if destination else ""
    tail = f"({summary.skipped} skipped, {plural(summary.errors, 'error')})"
    if summary.cancelled:
        verb = {"backup": "Backup", "export": "Export", "xmp": "XMP export"}.get(kind, kind.title())
        return (f"{verb} cancelled after {plural(done, noun)}{where} "
                f"({summary.skipped} skipped, {summary.errors} not run or failed)")
    verb = {"backup": "Backed up", "export": "Exported", "xmp": "Wrote"}.get(kind, "Completed")
    return f"{verb} {plural(done, noun)}{where} {tail}"


def _open_folder(path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass


class ImageManagerApp(tk.Tk):
    def __init__(self, initial_source: Path | None = None):
        super().__init__()
        self.title(NDEX_IMAGE_MANAGER_TITLE)
        self.geometry("1320x820")
        self.minsize(1040, 680)
        self.brand_images: list[tk.PhotoImage] = []
        apply_window_icon(self, self.brand_images)

        self.source_dir: Path | None = None
        self.catalog: Catalog | None = None
        # Every file in the catalog, grouped into shots. self.records is what the list
        # shows: one primary file per shot (combined) or every file (split).
        self.all_records: list[ImageRecord] = []
        self.shots: dict[str, Shot] = {}
        self.records: list[ImageRecord] = []
        self._rows: dict[str, ImageRecord] = {}
        self._records_by_id: dict[int, ImageRecord] = {}
        self.current_record: ImageRecord | None = None
        self.undo_stack = UndoStack(UNDO_LIMIT)
        self._catalog_source: Path | None = None
        self._scan_generation = 0
        self._worker: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._active_job: str | None = None
        self._closing = False
        self._queue_job: str | None = None
        self.preview_image: ImageTk.PhotoImage | None = None
        self.fullscreen_image: ImageTk.PhotoImage | None = None
        self.thumbnail_images: dict[int, ImageTk.PhotoImage] = {}
        self.star_labels: list[tk.Label] = []
        self._preview_resize_job: str | None = None
        self.ui_queue: queue.Queue = queue.Queue()
        self._last_progress_emit = 0.0
        self._stale_ids: set[int] = set()
        self._job_destination: Path | None = None
        self._menu_hint_active = False

        self.file_filter = tk.StringVar(value="all")
        self.pick_filter = tk.StringVar(value="all")
        self.rating_filter = tk.StringVar(value="0")
        self.file_filter_label = tk.StringVar()
        self.pick_filter_label = tk.StringVar()
        self.rating_filter_label = tk.StringVar()
        for variable in (self.file_filter, self.pick_filter, self.rating_filter):
            variable.trace_add("write", self._sync_filter_labels)
        self._sync_filter_labels()
        try:
            stored_advance = get_section(SETTINGS_SECTION).get("advance_after_mark", True)
        except OSError:
            stored_advance = True
        self.advance_after_mark = tk.BooleanVar(value=bool(stored_advance))
        try:
            stored_combine = get_section(SETTINGS_SECTION).get("combine_pairs", True)
        except OSError:
            stored_combine = True
        self.combine_pairs = tk.BooleanVar(value=bool(stored_combine))
        self.sort_key = tk.StringVar(value="capture_datetime")
        self.sort_descending = tk.BooleanVar(value=False)
        self.detail_mode = tk.StringVar(value="Simple")
        self.image_layout = tk.StringVar(value="50%")
        self.preview_background = tk.StringVar(value="Dark Gray")
        self.status = tk.StringVar(value="Choose a shooting folder to start culling.")
        self.selection_status = tk.StringVar(value="0 selected")
        self.folder_status = tk.StringVar(value="No folder selected")
        self.catalog_status = tk.StringVar(value="0 shown")
        self.summary_text = tk.StringVar(value="Select an image to see EXIF summary.")

        apply_tk_theme(self)
        self._build_menu()
        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._queue_job = self.after(100, self._process_ui_queue)

        if initial_source is not None:
            self.after(200, lambda: self._open_initial_source(Path(initial_source)))

    def _open_initial_source(self, source_dir: Path) -> None:
        if not self._can_start_work():
            return
        if not source_dir.is_dir():
            messagebox.showwarning(
                NDEX_IMAGE_MANAGER_TITLE,
                f"Handoff folder does not exist:\n{source_dir}",
            )
            return
        self.source_dir = source_dir
        self.folder_status.set(source_dir.name)
        self._remember_last_folder()
        self.scan_folder()

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=0)
        busy_actions: list[int] = []

        def add_action(label: str, command, accelerator: str | None = None, busy_sensitive: bool = True) -> None:
            options = {"label": label, "command": command}
            if accelerator:
                options["accelerator"] = accelerator
            file_menu.add_command(**options)
            if busy_sensitive:
                busy_actions.append(file_menu.index("end"))

        add_action("Choose Folder\u2026", self.choose_folder, "Ctrl+O")
        add_action("Reopen Last Folder", self.reopen_last_folder)
        add_action("Rescan", self.rescan, "F5")
        file_menu.add_separator()
        add_action("Export Selected\u2026", self.open_export_dialog, "Ctrl+E")
        add_action("Backup Picked\u2026", self.backup_picked)
        add_action("Write XMP Sidecars (for Lightroom/Evoto)", self.export_xmp_sidecars)
        add_action("Send Picks to Auto Selector", self.send_to_auto_selector)
        add_action("Send Picks to Frame", self.send_picks_to_frame)
        file_menu.add_separator()
        add_action("Job Results\u2026", self.open_job_results, busy_sensitive=False)
        file_menu.add_separator()
        add_action("Exit", self.destroy, busy_sensitive=False)
        self.file_menu = file_menu
        self._file_action_indices = busy_actions
        file_menu.bind("<<MenuSelect>>", self._on_file_menu_select)
        menu_bar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menu_bar, tearoff=0, postcommand=self._update_undo_menu)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo, state=tk.DISABLED)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo, state=tk.DISABLED)
        self.edit_menu = edit_menu
        menu_bar.add_cascade(label="Edit", menu=edit_menu)

        selection_menu = tk.Menu(menu_bar, tearoff=0)
        selection_menu.add_command(label="Select All Visible", accelerator="Ctrl+A", command=self.select_all_visible)
        selection_menu.add_command(label="Full Screen Preview", accelerator="F", command=self.open_fullscreen_viewer)
        menu_bar.add_cascade(label="Selection", menu=selection_menu)

        filter_menu = tk.Menu(menu_bar, tearoff=0)
        type_menu = tk.Menu(filter_menu, tearoff=0)
        for value, label in FILE_FILTER_LABELS:
            type_menu.add_radiobutton(
                label=label,
                variable=self.file_filter,
                value=value,
                command=self.refresh_records,
            )
        pick_menu = tk.Menu(filter_menu, tearoff=0)
        for value, label in PICK_FILTER_LABELS:
            pick_menu.add_radiobutton(
                label=label,
                variable=self.pick_filter,
                value=value,
                command=self.refresh_records,
            )
        rating_menu = tk.Menu(filter_menu, tearoff=0)
        for value, label in RATING_FILTER_LABELS:
            rating_menu.add_radiobutton(
                label=label,
                variable=self.rating_filter,
                value=value,
                command=self.refresh_records,
            )
        filter_menu.add_cascade(label="Type", menu=type_menu)
        filter_menu.add_cascade(label="Pick", menu=pick_menu)
        filter_menu.add_cascade(label="Rating", menu=rating_menu)
        filter_menu.add_separator()
        filter_menu.add_command(label="Clear Filters", command=self.clear_filters)
        menu_bar.add_cascade(label="Filter", menu=filter_menu)

        view_menu = tk.Menu(menu_bar, tearoff=0)
        exif_menu = tk.Menu(view_menu, tearoff=0)
        for value in ("Simple", "Full"):
            exif_menu.add_radiobutton(
                label=value,
                variable=self.detail_mode,
                value=value,
                command=lambda: self._show_details(self.current_record),
            )
        layout_menu = tk.Menu(view_menu, tearoff=0)
        for value in ("50%", "80%", "Full"):
            layout_menu.add_radiobutton(
                label=value,
                variable=self.image_layout,
                value=value,
                command=self.apply_layout_preset,
            )
        background_menu = tk.Menu(view_menu, tearoff=0)
        for value in PREVIEW_BACKGROUNDS:
            background_menu.add_radiobutton(
                label=value,
                variable=self.preview_background,
                value=value,
                command=self.apply_preview_background,
            )
        view_menu.add_cascade(label="EXIF Detail", menu=exif_menu)
        view_menu.add_cascade(label="Image Layout", menu=layout_menu)
        view_menu.add_cascade(label="Preview Background", menu=background_menu)
        view_menu.add_separator()
        view_menu.add_checkbutton(
            label="Show RAW+JPG as one row",
            variable=self.combine_pairs,
            command=self._on_combine_toggled,
        )
        view_menu.add_checkbutton(
            label="Advance after Pick/Reject/Rating",
            variable=self.advance_after_mark,
            command=self._save_advance_setting,
        )
        menu_bar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(label="Shortcuts", command=self.show_shortcuts)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.configure(menu=menu_bar)

    def _build_ui(self) -> None:
        header = build_app_header(
            self,
            title=NDEX_IMAGE_MANAGER_TITLE,
            tagline="Browse, rate, select, and export",
            holder=self.brand_images,
        )
        header.pack(fill=tk.X)
        info = ttk.Frame(header, style="Header.TFrame")
        info.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))
        folder_label = ttk.Label(info, textvariable=self.folder_status, style="Muted.TLabel", width=26, anchor="e")
        folder_label.pack(anchor=tk.E)
        Tooltip(folder_label, lambda: str(self.source_dir) if self.source_dir else self.folder_status.get())
        ttk.Label(info, textvariable=self.catalog_status, style="Muted.TLabel", width=26, anchor="e").pack(anchor=tk.E)

        toolbar_outer = ttk.Frame(self, padding=(16, 0, 16, 10))
        toolbar_outer.pack(fill=tk.X)
        toolbar = ttk.Frame(toolbar_outer, padding=(12, 8), style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X)

        self.choose_button = ttk.Button(toolbar, text="Choose Folder\u2026", command=self.choose_folder)
        self.choose_button.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(toolbar, text="Show", style="Toolbar.TLabel").pack(side=tk.LEFT)
        file_filter = ttk.Combobox(
            toolbar,
            textvariable=self.file_filter_label,
            values=[label for _value, label in FILE_FILTER_LABELS],
            width=16,
            state="readonly",
        )
        file_filter.pack(side=tk.LEFT, padx=(6, 12))
        file_filter.bind("<<ComboboxSelected>>", lambda event: self._on_filter_chosen(self.file_filter, FILE_FILTER_LABELS, file_filter))
        self.file_filter_widget = file_filter

        pick_filter = ttk.Combobox(
            toolbar,
            textvariable=self.pick_filter_label,
            values=[label for _value, label in PICK_FILTER_LABELS],
            width=14,
            state="readonly",
        )
        pick_filter.pack(side=tk.LEFT, padx=(0, 12))
        pick_filter.bind("<<ComboboxSelected>>", lambda event: self._on_filter_chosen(self.pick_filter, PICK_FILTER_LABELS, pick_filter))
        self.pick_filter_widget = pick_filter

        rating_filter = ttk.Combobox(
            toolbar,
            textvariable=self.rating_filter_label,
            values=[label for _value, label in RATING_FILTER_LABELS],
            width=11,
            state="readonly",
        )
        rating_filter.pack(side=tk.LEFT, padx=(0, 14))
        rating_filter.bind("<<ComboboxSelected>>", lambda event: self._on_filter_chosen(self.rating_filter, RATING_FILTER_LABELS, rating_filter))
        self.rating_filter_widget = rating_filter

        self._build_culling_actions(toolbar_outer)

        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))

        self.left_pane = ttk.Frame(self.paned, padding=0, style="Card.TFrame")
        self.paned.add(self.left_pane, weight=1)
        self.right_pane = ttk.Frame(self.paned, padding=0, style="Card.TFrame")
        self.paned.add(self.right_pane, weight=1)

        columns = tuple(TREE_COLUMNS.keys())
        self.tree = ttk.Treeview(self.left_pane, columns=columns, show="headings", selectmode="extended")
        self._col_widths = self._measure_columns()
        for column in columns:
            config = TREE_COLUMNS[column]
            self.tree.heading(column, text=config["label"], command=lambda name=column: self.sort_by_column(name))
            self.tree.column(
                column,
                width=self._col_widths[column][0],
                minwidth=self._col_widths[column][1],
                stretch=config["stretch"],
                anchor=config.get("anchor", tk.W),
            )
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=(0, 1), pady=0)
        scrollbar = ttk.Scrollbar(self.left_pane, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(fill=tk.Y, side=tk.LEFT)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        for pick_status, tint in PICK_TINTS.items():
            self.tree.tag_configure(pick_status, background=tint)
        # Tree-level bindings stop the Treeview class binding from moving a
        # second row; the root binding handles focus elsewhere.
        for key, offset in (("Up", -1), ("Down", 1), ("Left", -1), ("Right", 1)):
            self.tree.bind(f"<{key}>", lambda event, step=offset: self._on_arrow(event, step))
        self.tree.bind("<Configure>", self._fit_name_column, add="+")
        self.paned.bind("<Configure>", self._ensure_list_width, add="+")
        self._build_empty_state()

        # The details block is packed first (bottom) so a small window shrinks the
        # preview before it clips the stars or EXIF text.
        self.details_frame = tk.Frame(self.right_pane, bg=CARD_BG, bd=0, highlightthickness=0)

        preview_frame = tk.Frame(
            self.right_pane, bg=self._preview_background_color(), bd=0, highlightthickness=0,
            width=200, height=self._scaled(72),
        )
        preview_frame.pack_propagate(False)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        self.preview_frame = preview_frame
        self.preview_label = tk.Label(
            preview_frame,
            text="No preview",
            anchor=tk.CENTER,
            bg=self._preview_background_color(),
            fg="#cbd5e1",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            wraplength=360,
        )
        self.preview_label.pack(fill=tk.BOTH, expand=True)
        self.preview_label.bind("<Double-Button-1>", lambda event: self.open_fullscreen_viewer())
        self.preview_label.bind("<Configure>", lambda event: self._schedule_preview_refresh())
        # Preview keeps its minimum height; the details block gives way (its text
        # area is the bottom-most part and clips first).
        self.details_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(1, 0))

        details_header = tk.Frame(self.details_frame, bg=CARD_BG, bd=0, highlightthickness=0)
        details_header.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(
            details_header,
            text="EXIF / Selection",
            bg=CARD_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            bd=0,
            highlightthickness=0,
        ).pack(side=tk.LEFT)

        self.summary_label = tk.Label(
            self.details_frame,
            textvariable=self.summary_text,
            bg=CARD_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI", 9, "bold"),
            anchor=tk.W,
            justify=tk.LEFT,
            bd=0,
            highlightthickness=0,
            wraplength=400,
        )
        self.summary_label.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.details_frame.bind(
            "<Configure>",
            lambda event: self.summary_label.configure(wraplength=max(event.width - 28, 120)),
        )

        rating_row = tk.Frame(self.details_frame, bg=CARD_BG, bd=0, highlightthickness=0)
        rating_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        for rating in range(1, 6):
            star = tk.Label(
                rating_row,
                text=STAR_EMPTY,
                font=("Segoe UI Symbol", 15),
                cursor="hand2",
                padx=0,
                bg=CARD_BG,
                fg="#6b7280",
                bd=0,
                highlightthickness=0,
            )
            star.pack(side=tk.LEFT)
            star.bind("<Button-1>", lambda event, value=rating: self.set_rating(value, advance=False))
            self.star_labels.append(star)
        ttk.Button(rating_row, text="Clear", command=lambda: self.set_rating(0, advance=False)).pack(side=tk.LEFT, padx=(8, 0))

        text_row = tk.Frame(self.details_frame, bg=CARD_BG, bd=0, highlightthickness=0)
        text_row.pack(fill=tk.X, pady=(0, 10))
        self.detail_text = tk.Text(
            text_row,
            height=6,
            wrap=tk.WORD,
            bg=CARD_BG,
            fg=TEXT_PRIMARY,
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            padx=12,
            pady=4,
        )
        detail_scroll = ttk.Scrollbar(text_row, orient=tk.VERTICAL, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.detail_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        style_text_widget(self.detail_text)
        self.detail_text.configure(state=tk.DISABLED)

        bottom = ttk.Frame(self, padding=(16, 0, 16, 12), style="Footer.TFrame")
        # Packed ahead of the paned window so a short window shrinks the panes,
        # never the status footer.
        bottom.pack(side=tk.BOTTOM, fill=tk.X, before=self.paned)
        status_row = ttk.Frame(bottom, style="Footer.TFrame")
        status_row.pack(fill=tk.X, pady=(0, 4))
        self.cancel_button = ttk.Button(status_row, text="Cancel", command=self.cancel_work, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.work_progress = ttk.Progressbar(status_row, length=170, mode="determinate")
        self.work_progress.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Label(status_row, textvariable=self.status, style="Muted.TLabel", anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.footer = bottom
        self.footer_info_row = ttk.Frame(bottom, style="Footer.TFrame")
        self.footer_info_row.pack(fill=tk.X)
        self.footer_hint_row = ttk.Frame(bottom, style="Footer.TFrame")
        self.selection_label = ttk.Label(self.footer_info_row, textvariable=self.selection_status, style="Muted.TLabel")
        self.selection_label.pack(side=tk.LEFT)
        # Parent is the footer itself so it can be packed into either row.
        self.hint_label = ttk.Label(bottom, text=SHORTCUT_HINT, style="Muted.TLabel")
        self.hint_label.pack(in_=self.footer_info_row, side=tk.RIGHT)
        self._hint_below = False
        bottom.bind("<Configure>", self._layout_footer_hint)
        self.after(100, self.apply_layout_preset)
        self.after(120, self.apply_preview_background)
        self._update_culling_actions()

    def _build_culling_actions(self, parent: ttk.Frame) -> None:
        self.actions_toolbar = ttk.Frame(parent, padding=(12, 0, 12, 8), style="Toolbar.TFrame")
        self.actions_toolbar.pack(fill=tk.X)
        self.actions_toolbar.columnconfigure(1, weight=1)
        self.mark_actions = ttk.Frame(self.actions_toolbar, style="CardInner.TFrame")
        self.mark_actions.grid(row=0, column=0, sticky="w")
        self.mark_buttons: dict[str, ttk.Button] = {}
        for status, text in (("Pick", "Pick (P)"), ("Maybe", "Maybe (M)"),
                             ("Reject", "Reject (X)"), ("Unrated", "Clear (U)")):
            button = ttk.Button(
                self.mark_actions, text=text, width=0,
                command=lambda mark=status: self.set_pick(mark),
            )
            button.pack(side=tk.LEFT, padx=(0, 6))
            self.mark_buttons[status] = button
        Tooltip(self.mark_buttons["Unrated"], "Clear the pick flag for the selected photos; keep their star ratings.")

        self.workflow_actions = ttk.Frame(self.actions_toolbar, style="CardInner.TFrame")
        self.workflow_actions.grid(row=0, column=1, sticky="e")
        self.export_button = ttk.Button(
            self.workflow_actions, text="Export Selected\u2026", width=0, command=self.open_export_dialog)
        self.export_button.pack(side=tk.LEFT, padx=(0, 14))
        ttk.Label(self.workflow_actions, text="Send picks to", style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self.send_selector_button = ttk.Button(
            self.workflow_actions, text="Auto Selector", width=0, command=self.send_to_auto_selector)
        self.send_selector_button.pack(side=tk.LEFT, padx=(0, 6))
        self.send_frame_button = ttk.Button(
            self.workflow_actions, text="Frame", width=0, command=self.send_picks_to_frame)
        self.send_frame_button.pack(side=tk.LEFT)
        for button, label in (
            (self.export_button, "Export Selected\u2026"),
            (self.send_selector_button, "Send Picks to Auto Selector"),
            (self.send_frame_button, "Send Picks to Frame"),
        ):
            Tooltip(button, MENU_HINTS[label])
        self._actions_stacked = False
        self.actions_toolbar.bind("<Configure>", self._layout_culling_actions)

    def _layout_culling_actions(self, event=None) -> None:
        width = event.width if event is not None else self.actions_toolbar.winfo_width()
        needed = self.mark_actions.winfo_reqwidth() + self.workflow_actions.winfo_reqwidth() + 40
        stacked = width < needed
        if stacked != self._actions_stacked:
            self._actions_stacked = stacked
            self.workflow_actions.grid_configure(
                row=1 if stacked else 0, column=0 if stacked else 1,
                columnspan=2 if stacked else 1, sticky="w" if stacked else "e",
                pady=(6, 0) if stacked else 0,
            )

    def _update_culling_actions(self) -> None:
        idle = self._active_job is None and not self._closing
        can_mark = self._can_mark()
        has_selection = self.catalog is not None and bool(self.tree.selection())
        for button in self.mark_buttons.values():
            button.configure(state=tk.NORMAL if can_mark and has_selection else tk.DISABLED)
        self.export_button.configure(state=tk.NORMAL if idle and has_selection else tk.DISABLED)
        for button in (self.send_selector_button, self.send_frame_button):
            button.configure(state=tk.NORMAL if idle and self.catalog is not None else tk.DISABLED)
        self._update_undo_menu()

    def _can_mark(self) -> bool:
        """Culling stays available while a scan streams rows in; other jobs lock the marks."""
        return not self._closing and self._active_job in (None, "scan")

    def _bind_shortcuts(self) -> None:
        for key, status in (("p", "Pick"), ("m", "Maybe"), ("x", "Reject"), ("u", "Unrated")):
            for letter in (key, key.upper()):
                self.bind(f"<{letter}>", lambda event, mark=status:
                          self._on_photo_shortcut(event, self.set_pick, mark))
        for value in range(0, 6):
            self.bind(str(value), lambda event, rating=value:
                      self._on_photo_shortcut(event, self.set_rating, rating))
        self.bind("<Down>", lambda event: self._on_arrow(event, 1))
        self.bind("<Right>", lambda event: self._on_arrow(event, 1))
        self.bind("<Up>", lambda event: self._on_arrow(event, -1))
        self.bind("<Left>", lambda event: self._on_arrow(event, -1))
        self.bind("<f>", lambda event: self._on_photo_shortcut(event, self.open_fullscreen_viewer))
        self.bind("<F>", lambda event: self._on_photo_shortcut(event, self.open_fullscreen_viewer))
        self.bind("<Control-a>", lambda event: self._on_photo_shortcut(event, self.select_all_visible))
        self.bind("<Control-o>", lambda event: self.choose_folder())
        self.bind("<Control-e>", lambda event: self.open_export_dialog())
        self.bind("<F5>", lambda event: self.rescan())
        self.bind("<Escape>", lambda event: self._on_escape(event))
        for sequence in ("<Control-z>", "<Control-Z>"):
            self.bind(sequence, lambda event: self._on_photo_shortcut(event, self.undo))
        for sequence in ("<Control-y>", "<Control-Y>", "<Control-Shift-z>", "<Control-Shift-Z>"):
            self.bind(sequence, lambda event: self._on_photo_shortcut(event, self.redo))

    # ---- filters, arrows, menu hints, empty state ----

    def _on_escape(self, event):
        # Esc cancels a running scan; other jobs keep their Cancel button only.
        if self._active_job == "scan":
            self.cancel_work()
            return "break"
        return None

    def _on_photo_shortcut(self, event, command, *args):
        if event.widget.winfo_class() in TEXT_INPUT_CLASSES:
            return None
        command(*args)
        return "break"

    def _measure_columns(self) -> dict[str, tuple[int, int]]:
        """(width, minwidth) per column, measured from the real fonts so text never clips."""
        style = ttk.Style(self)
        body = tkfont.Font(self, font=style.lookup("Treeview", "font") or "TkDefaultFont")
        head = tkfont.Font(self, font=style.lookup("Treeview.Heading", "font") or "TkDefaultFont")
        pad = self._scaled(8)

        def fit(sample: str, header: str = "") -> int:
            # Only the sorted column carries an arrow; give Date room for it.
            arrow = " \u2191" if header == "Date" else ""
            header_width = head.measure(header + arrow) + pad if header else 0
            return max(body.measure(sample) + pad, header_width)

        fixed = {
            "state": body.measure("\u2715") + pad,
            "type": fit("RAW+JPG", "Type"),
            "pick": fit("Unrated", "Pick"),
            "rating": fit(STAR_FILLED * 5, STAR_FILLED),
            "date": fit("00-00 00:00", "Date"),
        }
        widths = {key: (value, value) for key, value in fixed.items()}
        name_min = body.measure("IMG_0000.CR3") + pad
        widths["name"] = (int(name_min * 1.3), name_min)
        return widths

    def _scaled(self, pixels: int) -> int:
        """Column widths are pixels while fonts follow Windows display scaling."""
        try:
            factor = float(self.tk.call("tk", "scaling")) * 72.0 / 96.0
        except (tk.TclError, ValueError):
            factor = 1.0
        return int(round(pixels * max(factor, 1.0)))

    def _list_needed_width(self) -> int:
        return sum(minimum for _width, minimum in self._col_widths.values()) + self._scaled(16)

    def _layout_footer_hint(self, _event=None) -> None:
        """Keep the shortcut hint beside the selection count, or below it if too narrow."""
        needed = self.selection_label.winfo_reqwidth() + self.hint_label.winfo_reqwidth() + 40
        fits = self.footer.winfo_width() >= needed
        if fits and self._hint_below:
            self._hint_below = False
            self.hint_label.pack_forget()
            self.footer_hint_row.pack_forget()
            self.hint_label.pack(in_=self.footer_info_row, side=tk.RIGHT)
        elif not fits and not self._hint_below:
            self._hint_below = True
            self.hint_label.pack_forget()
            self.footer_hint_row.pack(fill=tk.X)
            self.hint_label.pack(in_=self.footer_hint_row, side=tk.LEFT)

    def _ensure_list_width(self, _event=None) -> None:
        if self.image_layout.get() != "50%" or len(self.paned.panes()) < 2:
            return
        width = self.paned.winfo_width()
        needed = min(self._list_needed_width(), int(width * 0.72))
        try:
            if width > 1 and self.paned.sashpos(0) < needed:
                self.paned.sashpos(0, needed)
        except tk.TclError:
            pass

    def _fit_name_column(self, _event=None) -> None:
        """Let the File column take whatever the fixed columns leave over."""
        others = sum(width for key, (width, _minimum) in self._col_widths.items() if key != "name")
        available = self.tree.winfo_width() - others - 4
        self.tree.column("name", width=max(self._col_widths["name"][1], available))

    def _sync_filter_labels(self, *_args) -> None:
        self.file_filter_label.set(label_for(FILE_FILTER_LABELS, self.file_filter.get()))
        self.pick_filter_label.set(label_for(PICK_FILTER_LABELS, self.pick_filter.get()))
        self.rating_filter_label.set(label_for(RATING_FILTER_LABELS, self.rating_filter.get()))

    def _on_filter_chosen(self, variable: tk.StringVar, options, widget) -> None:
        variable.set(value_for(options, widget.get()))
        self.refresh_records()

    def _min_rating(self) -> int:
        try:
            return max(0, int(self.rating_filter.get()))
        except ValueError:
            return 0

    def _filters_active(self) -> bool:
        return (
            self.file_filter.get() != "all"
            or self.pick_filter.get() != "all"
            or self._min_rating() > 0
        )

    def clear_filters(self) -> None:
        self.file_filter.set("all")
        self.pick_filter.set("all")
        self.rating_filter.set("0")
        self.refresh_records()

    def _on_arrow(self, event, offset: int):
        """Move exactly one row, unless a text-input widget owns the key."""
        widget_class = ""
        try:
            widget_class = event.widget.winfo_class()
        except (AttributeError, tk.TclError):
            pass
        # Shift/Ctrl+arrow keep their native Treeview behaviour (range select).
        if widget_class in TEXT_INPUT_CLASSES or getattr(event, "state", 0) & 0x5:
            return None
        self.move_selection(offset)
        return "break"

    def _save_advance_setting(self) -> None:
        try:
            update_section(SETTINGS_SECTION, {"advance_after_mark": bool(self.advance_after_mark.get())})
        except OSError:
            pass

    def _on_file_menu_select(self, _event=None) -> None:
        try:
            index = self.file_menu.index("active")
            label = self.file_menu.entrycget(index, "label") if isinstance(index, int) else ""
        except tk.TclError:
            label = ""
        hint = MENU_HINTS.get(label)
        if hint:
            if not self._menu_hint_active:
                self._status_before_menu = self.status.get()
            self._menu_hint_active = True
            self.status.set(hint)
        elif self._menu_hint_active:
            self._menu_hint_active = False
            self.status.set(getattr(self, "_status_before_menu", ""))

    def _build_empty_state(self) -> None:
        self.empty_overlay = tk.Frame(self.left_pane, bg=CARD_BG, bd=0, highlightthickness=0)
        inner = tk.Frame(self.empty_overlay, bg=CARD_BG, bd=0, highlightthickness=0)
        inner.place(relx=0.5, rely=0.42, anchor=tk.CENTER)
        self.empty_label = tk.Label(
            inner, text="", bg=CARD_BG, fg=TEXT_PRIMARY, font=("Segoe UI", 12),
            wraplength=300, justify=tk.CENTER, bd=0, highlightthickness=0,
        )
        self.empty_label.pack(pady=(0, 14))
        self.empty_button = ttk.Button(inner, text="", command=self.choose_folder, style="Accent.TButton")
        self.empty_button.pack()
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        kind = empty_state_kind(
            has_catalog=self.catalog is not None,
            scanning=self._active_job == "scan",
            record_count=len(self.records),
            filters_active=self._filters_active(),
        )
        if kind is None:
            self.empty_overlay.place_forget()
            return
        if kind == "start":
            text, button, command = "Choose a shooting folder to start culling", "Choose Folder\u2026 (Ctrl+O)", self.choose_folder
        elif kind == "filtered":
            text, button, command = "No photos match these filters.", "Clear Filters", self.clear_filters
        else:
            text, button, command = "No supported photos were found in this folder.", "Choose Another Folder\u2026", self.choose_folder
        self.empty_label.configure(text=text)
        self.empty_button.configure(text=button, command=command)
        self.empty_overlay.place(in_=self.tree, x=0, y=0, relwidth=1, relheight=1)
        self.empty_overlay.lift()

    def choose_folder(self) -> None:
        if not self._can_start_work():
            return
        selected = filedialog.askdirectory(title="Choose a shooting folder")
        if selected:
            self.source_dir = Path(selected)
            self.folder_status.set(self.source_dir.name)
            self._remember_last_folder()
            self.scan_folder()

    def reopen_last_folder(self) -> None:
        if not self._can_start_work():
            return
        stored = get_section(SETTINGS_SECTION)
        last_source = stored.get("last_source", "")
        if not last_source or not Path(last_source).is_dir():
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "No previous folder found.")
            return
        self.source_dir = Path(last_source)
        self.folder_status.set(self.source_dir.name)
        self.scan_folder()

    def _remember_last_folder(self) -> None:
        if self.source_dir is None:
            return
        try:
            update_section(SETTINGS_SECTION, {"last_source": str(self.source_dir)})
            from ndex_common.session import remember

            remember("image_manager", folders={"source": str(self.source_dir)})
        except OSError:
            pass

    def rescan(self) -> None:
        if not self.source_dir:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Choose a folder first.")
            return
        self.scan_folder()

    def scan_folder(self) -> None:
        if not self._can_start_work():
            return
        assert self.source_dir is not None
        if self.catalog:
            self.catalog.close()
            self.catalog = None
        if self._catalog_source != self.source_dir:
            # Marks made in another folder cannot be undone here.
            self.undo_stack.clear()
        self._catalog_source = self.source_dir
        self.status.set(f"Scanning {self.source_dir.name}\u2026")
        self._stale_ids.clear()
        self.tree.delete(*self.tree.get_children())
        self._clear_row_model()
        self.current_record = None
        self._show_preview(None)
        self._show_details(None)
        self._refresh_rating_widgets(0)
        self.update_selection_status()
        self.update_catalog_status()
        source = self.source_dir
        catalog_path = Path(source).resolve() / ".dsb_cache" / "catalog.sqlite"

        def work(cancel, progress):
            generation = self._scan_generation
            # Rows reach the list in batches while the scan keeps running.
            return ImageScanner().scan(
                source, recursive=True, progress_callback=progress, cancel_event=cancel,
                batch_callback=lambda batch: self.ui_queue.put(("scan_rows", generation, catalog_path, batch)),
            )

        self._start_worker("scan", work)

    def _can_start_work(self) -> bool:
        if self._closing:
            return False
        if self._active_job is not None:
            self.status.set("A task is running. Wait for it to finish or use Cancel.")
            return False
        return True

    def _set_work_controls(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        for index in self._file_action_indices:
            self.file_menu.entryconfigure(index, state=state)
        self.choose_button.configure(state=state)
        self.file_filter_widget.configure(state=tk.DISABLED if busy else "readonly")
        self.pick_filter_widget.configure(state=tk.DISABLED if busy else "readonly")
        self.rating_filter_widget.configure(state=tk.DISABLED if busy else "readonly")
        self.cancel_button.configure(state=tk.NORMAL if busy else tk.DISABLED)
        if busy:
            self.work_progress.configure(mode="indeterminate", value=0)
            self.work_progress.start(15)
        else:
            self.work_progress.stop()
            self.work_progress.configure(mode="determinate", value=0)
        self._update_empty_state()

        self._update_culling_actions()

    def _start_worker(self, kind: str, work) -> None:
        self._active_job = kind
        self._cancel_event = threading.Event()
        self._scan_generation += 1
        generation = self._scan_generation
        cancel = self._cancel_event
        self._last_progress_emit = 0.0
        self._set_work_controls(True)

        def run() -> None:
            result, error, cancelled = None, None, False
            try:
                result = work(cancel, lambda index, total, path: self._queue_work_progress(
                    generation, index, total, path,
                ))
            except ScanCancelled as exc:
                cancelled, result = True, exc
            except Exception as exc:
                error = str(exc)
            self.ui_queue.put(("work_done", generation, kind, result, error, cancelled))

        self._worker = threading.Thread(target=run, name=f"image-manager-{kind}", daemon=False)
        self._worker.start()

    def _queue_work_progress(self, generation: int, index: int, total: int, path: Path) -> None:
        now = time.monotonic()
        if index < total and (now - self._last_progress_emit) < 0.1:
            return
        self._last_progress_emit = now
        self.ui_queue.put(("work_progress", generation, index, total, path.name))

    def cancel_work(self) -> None:
        if self._active_job is None:
            return
        self._cancel_event.set()
        self.cancel_button.configure(state=tk.DISABLED)
        message = "Cancelling after the current file or metadata batch finishes..."
        self.status.set(f"Closing: {message}" if self._closing else message)

    def destroy(self) -> None:
        if self._active_job is not None:
            self._closing = True
            self.cancel_work()
            return
        self._closing = True
        if self.catalog:
            self.catalog.close()
            self.catalog = None
        if self._queue_job is not None:
            self.after_cancel(self._queue_job)
            self._queue_job = None
        # Layout/preview callbacks also belong to this window. Cancelling them
        # avoids callbacks into destroyed widgets when another Tk window lives.
        for callback in self.tk.call("after", "info"):
            self.after_cancel(callback)
        super().destroy()

    def _process_ui_queue(self) -> None:
        self._queue_job = None
        while True:
            try:
                event = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if event[1] != self._scan_generation:
                continue
            try:
                if not self._dispatch_work_event(event):
                    return
            except Exception as exc:
                self.status.set(f"Could not update the task view: {exc}")
                messagebox.showerror(NDEX_IMAGE_MANAGER_TITLE, f"Could not update the task view:\n{exc}")
        self._queue_job = self.after(100, self._process_ui_queue)

    def _dispatch_work_event(self, event) -> bool:
        kind = event[0]
        if kind == "scan_rows":
            _, _generation, catalog_path, batch = event
            self._ingest_scan_rows(catalog_path, batch)
        elif kind == "work_progress":
            _, _generation, index, total, name = event
            if index > 0:
                self.work_progress.stop()
                self.work_progress.configure(mode="determinate", maximum=max(total, 1), value=index)
            if not self._cancel_event.is_set():
                self.status.set(progress_text(self._active_job or "scan", index, total, name))
        elif kind == "work_done":
            _, _generation, task, result, error, cancelled = event
            # A completion is queued only after file I/O and report saving.
            if self._worker:
                self._worker.join()
            self._worker = None
            self._active_job = None
            self._set_work_controls(False)
            if self._closing:
                problems = [error] if error else []
                if task != "scan" and result is not None:
                    summary, warnings = result
                    problems.extend(summary.messages[:10])
                    problems.extend(warnings)
                if problems:
                    messagebox.showwarning(
                        "Closing Image Manager",
                        "The task finished with problems:\n\n" + "\n".join(problems),
                    )
                self.destroy()
                return False
            if error:
                self.status.set(f"{KIND_NAMES.get(task, task.title())} failed.")
                messagebox.showerror(f"{KIND_NAMES.get(task, task.title())} failed", error)
            elif task == "scan":
                if cancelled:
                    self._scan_stopped(result)
                else:
                    self._scan_finished(result.catalog_path)
            else:
                self._operation_finished(task, *result)
        return True

    def _open_catalog(self, catalog_path: Path) -> None:
        if self.catalog is not None and Path(self.catalog.db_path) == Path(catalog_path):
            return
        if self.catalog:
            self.catalog.close()
        self.catalog = Catalog(Path(catalog_path))

    def _reconcile_pair_marks(self) -> str:
        """Older catalogs marked RAW and JPG separately; merge them into one state per shot."""
        assert self.catalog is not None
        fixed, files = self.catalog.reconcile_pair_marks()
        if not fixed:
            return ""
        log.info("Merged pick/rating marks of %d RAW+JPG shots (%d files updated)", fixed, files)
        return f" Merged RAW and JPG marks for {plural(fixed, 'shot')}."

    def _scan_finished(self, catalog_path: Path) -> None:
        self._open_catalog(catalog_path)
        merged = self._reconcile_pair_marks()
        self.refresh_records()
        self.status.set(ready_status_text(len(self.all_records), len(self.shots)) + merged)

    def _scan_stopped(self, stopped) -> None:
        """A cancelled scan keeps every file catalogued so far, ready to cull."""
        catalog_path = getattr(stopped, "catalog_path", None)
        if catalog_path is None and self.source_dir is not None:
            catalog_path = Path(self.source_dir).resolve() / ".dsb_cache" / "catalog.sqlite"
        if catalog_path is not None and Path(catalog_path).exists():
            self._open_catalog(catalog_path)
            self._reconcile_pair_marks()
            self.refresh_records()
        self.status.set(scan_stopped_text(getattr(stopped, "listed", 0), getattr(stopped, "total", 0)))

    # ---- row model: files -> shots -> list rows ----

    def _clear_row_model(self) -> None:
        self.all_records = []
        self.shots = {}
        self.records = []
        self._rows = {}
        self._records_by_id = {}

    def _load_records(self) -> None:
        assert self.catalog is not None
        self.all_records = self.catalog.list_images()
        self._records_by_id = {record.id: record for record in self.all_records}
        self.shots = build_shots(self.all_records)

    def _shot_of(self, record: ImageRecord) -> Shot:
        shot = self.shots.get(record.pair_group_id)
        if shot is not None and any(member is record for member in shot.records):
            return shot
        return Shot(record.pair_group_id, [record])

    def _row_records_for(self, shot: Shot) -> list[ImageRecord]:
        return [shot.primary] if self.combine_pairs.get() else list(shot.records)

    def _row_matches(self, record: ImageRecord) -> bool:
        """Does the row for this file pass the current list filters?"""
        shot = self._shot_of(record)
        file_filter, pick_filter, minimum = self.file_filter.get(), self.pick_filter.get(), self._min_rating()
        if self.combine_pairs.get():
            return shot_matches(shot, file_filter, pick_filter, minimum)
        if file_filter in ("raw", "jpg"):
            ok = record.media_type == file_filter
        elif file_filter in ("paired", "raw_only", "jpg_only"):
            ok = record.pair_status == {"paired": "raw_jpg_pair"}.get(file_filter, file_filter)
        elif file_filter == "proxy_failed":
            ok = record.proxy_status == "failed"
        else:
            ok = True
        return ok and record_matches_filters(shot, pick_filter, minimum)

    def _visible_records(self) -> list[ImageRecord]:
        sort_key, descending = self.sort_key.get(), self.sort_descending.get()
        if self.combine_pairs.get():
            matching = [shot for shot in self.shots.values() if self._row_matches(shot.primary)]
            return [shot.primary for shot in sort_shots(matching, sort_key, descending)]
        matching = [record for record in self.all_records if self._row_matches(record)]
        return sort_records(matching, sort_key, descending)

    def _row_values(self, record: ImageRecord) -> tuple:
        shot = self._shot_of(record)
        combined = self.combine_pairs.get()
        return (
            shot.pick_glyph,
            shot.stem if combined else record.display_name,
            shot.type_label if combined else record.type_label,
            shot.pick_status,
            STAR_FILLED * shot.rating if shot.rating > 0 else "",
            record.short_datetime,
        )

    def _row_tags(self, record: ImageRecord) -> tuple:
        return (self._shot_of(record).pick_status,)

    def _insert_row(self, record: ImageRecord) -> None:
        iid = str(record.id)
        self._rows[iid] = record
        self.tree.insert("", tk.END, iid=iid, values=self._row_values(record), tags=self._row_tags(record))

    def _ingest_scan_rows(self, catalog_path: Path, batch: list[ImageRecord]) -> None:
        """Add one streamed batch of freshly catalogued files to the list."""
        if self.catalog is None:
            self.catalog = Catalog(Path(catalog_path))
        touched: dict[str, Shot] = {}
        for record in batch:
            if record.id in self._records_by_id:
                continue
            self._records_by_id[record.id] = record
            self.all_records.append(record)
            shot = self.shots.get(record.pair_group_id)
            if shot is None:
                shot = self.shots[record.pair_group_id] = Shot(record.pair_group_id, [record])
            else:
                shot.records.append(record)
                shot.__post_init__()
            touched[record.pair_group_id] = shot
        had_rows = bool(self.tree.get_children())
        for shot in touched.values():
            for row in self._row_records_for(shot):
                if str(row.id) in self._rows:
                    self.tree.item(str(row.id), values=self._row_values(row), tags=self._row_tags(row))
                elif self._row_matches(row):
                    self.records.append(row)
                    self._insert_row(row)
        children = self.tree.get_children()
        if children and not had_rows:
            self._select_only(children[0])
        self.update_selection_status()
        self.update_catalog_status()

    def refresh_records(self, keep_shots: set[str] | None = None) -> None:
        if not self.catalog:
            return
        selection = self.tree.selection()
        focus = self.tree.focus()
        self._load_records()
        self.records = self._visible_records()
        self._stale_ids.clear()
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        self.current_record = None
        self._update_column_headings()
        for record in self.records:
            self._insert_row(record)
        if self.records:
            first = self.tree.get_children()[0]
            if keep_shots is not None:
                surviving = [iid for iid, row in self._rows.items() if row.pair_group_id in keep_shots]
            else:
                surviving = [iid for iid in selection if self.tree.exists(iid)]
            self.tree.selection_set(surviving or [first])
            focused = focus if focus in surviving else (surviving[0] if surviving else first)
            self.tree.focus(focused)
            self.tree.see(focused)
            self.on_select()
        else:
            self.status.set("No photos match these filters." if self._filters_active() else "No photos to show.")
            self._show_preview(None)
            self._show_details(None)
            self._refresh_rating_widgets(0)
        self.update_selection_status()
        self.update_catalog_status()
        self._update_empty_state()

    def _on_combine_toggled(self) -> None:
        try:
            update_section(SETTINGS_SECTION, {"combine_pairs": bool(self.combine_pairs.get())})
        except OSError:
            pass
        keep = {record.pair_group_id for record in self.selected_records()}
        self.refresh_records(keep_shots=keep or None)

    def sort_by_column(self, column: str) -> None:
        sort_key = TREE_COLUMNS[column]["sort_key"]
        if self.sort_key.get() == sort_key:
            self.sort_descending.set(not self.sort_descending.get())
        else:
            self.sort_key.set(sort_key)
            self.sort_descending.set(False)
        self.refresh_records()

    def _update_column_headings(self) -> None:
        current_sort = self.sort_key.get()
        for column, config in TREE_COLUMNS.items():
            label = config["label"]
            if config.get("indicator", True) and config["sort_key"] == current_sort:
                label = f"{label} {SORT_DESC if self.sort_descending.get() else SORT_ASC}"
            self.tree.heading(column, text=label, command=lambda name=column: self.sort_by_column(name))

    def update_catalog_status(self) -> None:
        folder = self.source_dir.name if self.source_dir else "No folder selected"
        self.folder_status.set(folder)
        text = f"{len(self.records)} shown"
        if self._filters_active():
            text += " (filtered)"
        self.catalog_status.set(text)

    def on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            self.update_selection_status()
            return
        focused = self.tree.focus()
        iid = focused if focused in selected else selected[-1]
        record = self._rows.get(iid)
        self.current_record = record
        self._prune_stale(selected)
        self._show_preview(record)
        self._show_details(record)
        self._refresh_rating_widgets(self._shot_of(record).rating if record else 0)
        self.update_selection_status()

    def _prune_stale(self, selected=()) -> None:
        """Drop rows that stopped matching the filters once the user navigates away."""
        if not self._stale_ids:
            return
        keep = {int(iid) for iid in selected}
        gone = {image_id for image_id in self._stale_ids if image_id not in keep}
        if not gone:
            return
        for image_id in gone:
            if self.tree.exists(str(image_id)):
                self.tree.delete(str(image_id))
            self._rows.pop(str(image_id), None)
        self.records = [record for record in self.records if record.id not in gone]
        self._stale_ids -= gone
        self.update_catalog_status()

    def set_pick(self, pick_status: str, advance: bool = True) -> None:
        self._apply_marks(pick_status=pick_status, advance=advance)

    def set_rating(self, rating: int, advance: bool = True) -> None:
        self._apply_marks(rating=rating, advance=advance)

    def _apply_marks(self, *, pick_status: str | None = None, rating: int | None = None, advance: bool = True) -> None:
        if not self._can_mark():
            if self._active_job is not None:
                self.status.set("A task is running. Wait for it to finish or use Cancel.")
            return
        if not self.catalog or not self.current_record or self.current_record.id is None:
            return
        rows = [record for record in self.selected_records() if record.id is not None]
        if not rows:
            return
        single = len(self.tree.selection()) == 1
        # A mark belongs to the shot: marking IMG_1.CR3 also marks IMG_1.JPG.
        shots = self._shots_of(rows)
        entries = []
        for shot in shots:
            for record in shot.records:
                if record.id is None:
                    continue
                new_pick = record.pick_status if pick_status is None else pick_status
                new_rating = record.rating if rating is None else rating
                if (new_pick, new_rating) != (record.pick_status, record.rating):
                    entries.append((record.id, record.pick_status, record.rating, new_pick, new_rating))
        if entries:
            self.catalog.set_marks((image_id, pick, stars) for image_id, _op, _or, pick, stars in entries)
            self._set_memory_marks((image_id, pick, stars) for image_id, _op, _or, pick, stars in entries)
            noun = "shot" if self.combine_pairs.get() else "file"
            self.undo_stack.push(MarkChange(mark_change_label(pick_status, rating, len(rows), noun), entries))
            self._update_undo_menu()
            if len(rows) > 1:
                self.status.set(f"{mark_done_text(pick_status, rating, len(rows), noun)} \u2014 Ctrl+Z to undo")
        next_iid = ""
        if advance and single and self.advance_after_mark.get():
            next_iid = self._next_row_after(rows[0])
        if self.sort_key.get() in RESORT_KEYS:
            # Row order depends on the changed field, so rebuild.
            self.refresh_records()
            if next_iid and self.tree.exists(next_iid):
                self._select_only(next_iid)
            return
        for shot in shots:
            for record in shot.records:
                iid = str(record.id)
                if not self.tree.exists(iid):
                    continue
                self.tree.item(iid, values=self._row_values(record), tags=self._row_tags(record))
                # A row that no longer matches stays until the user moves away.
                if self._row_matches(record):
                    self._stale_ids.discard(record.id)
                else:
                    self._stale_ids.add(record.id)
        if next_iid:
            self._select_only(next_iid)
            return
        self._show_details(self.current_record)
        self._refresh_rating_widgets(self._shot_of(self.current_record).rating)
        self.update_selection_status()

    def _shots_of(self, rows) -> list[Shot]:
        shots: dict[str, Shot] = {}
        for record in rows:
            shots.setdefault(record.pair_group_id, self._shot_of(record))
        return list(shots.values())

    def _set_memory_marks(self, marks) -> None:
        for image_id, pick, stars in marks:
            record = self._records_by_id.get(image_id)
            if record is not None:
                record.pick_status = pick  # type: ignore[assignment]
                record.rating = stars

    def _next_row_after(self, row: ImageRecord) -> str:
        """The row below, skipping other files of the same shot."""
        iid = self.tree.next(str(row.id))
        while iid and self._rows.get(iid) is not None and self._rows[iid].pair_group_id == row.pair_group_id:
            iid = self.tree.next(iid)
        return iid

    # ---- undo / redo ----

    def _update_undo_menu(self) -> None:
        if not hasattr(self, "edit_menu"):
            return
        usable = self.catalog is not None and self._can_mark()
        for index, name, label in ((0, "Undo", self.undo_stack.undo_label), (1, "Redo", self.undo_stack.redo_label)):
            self.edit_menu.entryconfigure(
                index, label=f"{name} {label}" if label else name,
                state=tk.NORMAL if usable and label else tk.DISABLED,
            )

    def undo(self) -> None:
        self._step_history(redo=False)

    def redo(self) -> None:
        self._step_history(redo=True)

    def _step_history(self, redo: bool) -> None:
        if not self._can_mark() or self.catalog is None:
            return
        change = self.undo_stack.pop_redo() if redo else self.undo_stack.pop_undo()
        if change is None:
            self.status.set("Nothing to redo." if redo else "Nothing to undo.")
            return
        if redo:
            marks = [(image_id, pick, stars) for image_id, _op, _or, pick, stars in change.entries]
        else:
            marks = [(image_id, pick, stars) for image_id, pick, stars, _np, _nr in change.entries]
        self.catalog.set_marks(marks)
        self._set_memory_marks(marks)
        combined = self.combine_pairs.get()
        row_ids: list[int] = []
        for image_id, _pick, _stars in marks:
            record = self._records_by_id.get(image_id)
            if record is None:
                continue
            row = self._shot_of(record).primary if combined else record
            if row.id not in row_ids:
                row_ids.append(row.id)
        self.refresh_records()
        if row_ids:
            self._restore_selection_ids(row_ids, row_ids[0])
        self.status.set(f"{'Redid' if redo else 'Undid'} {change.label}")
        self._update_undo_menu()

    def _select_only(self, iid: str) -> None:
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self.on_select()

    def move_selection(self, offset: int) -> None:
        children = list(self.tree.get_children())
        if not children:
            return
        selected = self.tree.selection()
        index = children.index(selected[0]) if selected else 0
        next_index = max(0, min(len(children) - 1, index + offset))
        self._select_only(children[next_index])

    def select_all_visible(self) -> str:
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children)
            self.tree.focus(children[0])
            self.on_select()
        return "break"

    def selected_records(self) -> list[ImageRecord]:
        selected = [self._rows[iid] for iid in self.tree.selection() if iid in self._rows]
        if selected:
            return selected
        return [self.current_record] if self.current_record else []

    def update_selection_status(self) -> None:
        selected_count = len(self.tree.selection())
        self.selection_status.set(selection_status_text(selected_count, len(self.records)))
        self._update_culling_actions()

    def show_shortcuts(self) -> None:
        messagebox.showinfo(
            "Shortcuts",
            "P  Pick\n"
            "X  Reject\n"
            "M  Maybe\n"
            "U  Clear pick (Unrated)\n"
            "0\u20135  Star rating (0 clears)\n"
            "\u2190 / \u2192 or \u2191 / \u2193  Move one photo\n"
            "F  Full screen (Esc to close)\n"
            "Ctrl+A  Select all shown\n"
            "Ctrl+O  Choose folder\n"
            "Ctrl+E  Export selected\n"
            "F5  Rescan\n\n"
            "Pick, reject and rating apply to all selected rows. With one row "
            "selected they advance to the next photo (View > Advance after "
            "Pick/Reject/Rating).",
        )

    def backup_picked(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Scan a folder first.")
            return
        shots = self.catalog.list_shots(pick_filter="Pick")
        if not shots:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "No picked images found. Set Pick first.")
            return
        destination = filedialog.askdirectory(title="Choose NDEX backup destination")
        if not destination:
            return
        if not messagebox.askyesno("Backup Picked", backup_confirm_text(shots, destination)):
            return
        # Every file of a picked shot (RAW and JPG) goes into the backup.
        self._start_operation("backup", shot_files(shots), Path(destination))

    def export_xmp_sidecars(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Scan a folder first.")
            return
        records = self.catalog.list_images()
        if not records:
            messagebox.showinfo(
                NDEX_IMAGE_MANAGER_TITLE,
                "No images found. Scan a shooting folder first.",
            )
            return
        # The XMP service gives every file of a shot the shot's single pick/rating state.
        self._start_operation("xmp", records, self.source_dir)

    def _start_operation(
        self, kind: str, records: list[ImageRecord], destination: Path,
        options: ExportOptions | None = None,
    ) -> None:
        # Keep paths, selections and options fixed for the entire job. Tk and
        # its SQLite connection are used only on the main thread.
        snapshots = [replace(record) for record in records]
        source = str(self.source_dir or "")
        catalog_path = self.catalog.db_path if self.catalog else None
        self._job_destination = destination
        self.status.set(f"Starting {KIND_NAMES.get(kind, kind).lower()} for {plural(len(snapshots), 'image')}\u2026")

        def work(cancel, progress):
            from ndex_common.workflow import record_job

            if kind == "backup":
                summary = BackupService().backup(snapshots, destination, cancel_event=cancel, progress_callback=progress)
                counts = {"copied": summary.copied, "overwritten": summary.overwritten}
            elif kind == "export":
                summary = ExportService().export(snapshots, options, cancel_event=cancel, progress_callback=progress)
                counts = {"exported": summary.exported, "overwritten": summary.overwritten}
            else:
                summary = XmpExportService().export(snapshots, cancel_event=cancel, progress_callback=progress)
                counts = {"written": summary.written}
            warnings = []
            if kind == "backup" and catalog_path:
                copied = {item["path"] for item in summary.items if item["status"] == "copied"}
                catalog = None
                try:
                    catalog = Catalog(catalog_path)
                    catalog.update_backup_statuses(
                        (record.id for record in snapshots if record.id is not None and str(record.file_path) in copied),
                        "backed_up",
                    )
                except Exception as exc:
                    warnings.append(f"Could not update catalog backup status: {exc}")
                finally:
                    if catalog:
                        catalog.close()
            context = {"cancelled": summary.cancelled, "operation": kind}
            if options:
                context.update(rename_pattern=options.rename_pattern, start_index=options.start_index,
                               duplicate_policy=options.duplicate_policy)
            try:
                report = record_job(
                    app="image_manager", type="export" if kind == "xmp" else kind,
                    source=source, destination=str(destination),
                    counts={**counts, "skipped": summary.skipped, "failed": summary.errors},
                    items=summary.items, folders={"source": source}, context=context,
                )
                if report is None:
                    warnings.append("Could not save Job Results. Check the NDEX application data folder.")
            except Exception as exc:
                warnings.append(f"Could not save Job Results: {exc}")
            return summary, warnings

        self._start_worker(kind, work)

    def _operation_finished(self, kind: str, summary, warnings: list[str]) -> None:
        if kind == "backup":
            self.refresh_records()
        finished = "cancelled" if summary.cancelled else "complete"
        destination = getattr(self, "_job_destination", None)
        message = operation_summary_text(kind, summary, destination)
        title = f"{KIND_NAMES.get(kind, kind.title())} {finished}"
        self.status.set(message)
        details = [message]
        if summary.cancelled:
            details.append("The active file finished safely. Unprocessed files are listed in Job Results.")
        elif kind == "xmp" and summary.written == 0 and summary.errors == 0:
            details.append("No picked or rated images found. Set pick status or rating first.")
        details.extend(summary.messages[:10])
        details.extend(warnings)
        problem = bool(summary.errors or warnings)
        produced = getattr(summary, "copied", getattr(summary, "exported", getattr(summary, "written", 0)))
        if not summary.cancelled and produced and destination is not None and Path(destination).is_dir():
            details.append("Open the destination folder?")
            if messagebox.askyesno(title, "\n\n".join(details), icon="warning" if problem else "info"):
                _open_folder(destination)
            return
        show = messagebox.showwarning if problem else messagebox.showinfo
        show(title, "\n\n".join(details))

    def send_to_auto_selector(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Scan a folder first.")
            return
        from ndex_common.manifest import frame_ready_paths
        from ndex_common.workflow import record_select_handoff

        # Hand over exactly the picked JPGs. Passing the whole folder would let
        # Auto Selector scan .dsb_cache thumbnails and select every RAW.
        shots = self.catalog.list_shots(pick_filter="Pick")
        files = frame_ready_paths(
            record.file_path
            for record in shot_files(shots)
            if record.media_type == "jpg" and Path(record.file_path).suffix.casefold() in (".jpg", ".jpeg")
        )
        without_jpg = sum(1 for shot in shots if not shot.has_jpg)
        if not files:
            note = f"\n\n{no_jpg_text(without_jpg, sent=True)}" if without_jpg else ""
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, f"No picked JPG files to send to Auto Selector.{note}")
            return
        question = send_confirm_text(len(files), "JPG", "Auto Selector")
        if without_jpg:
            question += f"\n\n{no_jpg_text(without_jpg)}"
        if not messagebox.askyesno("Send Picks to Auto Selector", question):
            return
        handoff = record_select_handoff(
            self.source_dir or files[0].parent, files, target="auto_selector"
        )
        if handoff is None:
            messagebox.showerror(
                NDEX_IMAGE_MANAGER_TITLE,
                "Could not write the handoff file, so the picks were not sent. "
                "Check that %LOCALAPPDATA%\\NDEX is writable.",
            )
            return
        args: list[str] = ["--open", "--handoff", str(handoff)]
        if self.source_dir is not None:
            args.extend(["--raw-source", str(self.source_dir)])
        launched = launch_app("auto_selector", args)
        if not launched:
            messagebox.showerror(
                NDEX_IMAGE_MANAGER_TITLE,
                "Could not find NDEX Auto Selector. Build or install it first.",
            )
        elif without_jpg:
            self.status.set(f"Sent {plural(len(files), 'picked JPG')}. {no_jpg_text(without_jpg, sent=True)}")

    def send_picks_to_frame(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Scan a folder first.")
            return
        from ndex_common.manifest import frame_ready_paths
        from ndex_common.workflow import record_select_handoff

        shots = self.catalog.list_shots(pick_filter="Pick")
        files = frame_ready_paths(record.file_path for record in shot_files(shots) if record.media_type == "jpg")
        if not files:
            files = frame_ready_paths(record.file_path for record in shot_files(shots))
        if not files:
            messagebox.showinfo(
                NDEX_IMAGE_MANAGER_TITLE,
                "No picked JPG/PNG/TIFF files to send. Frame does not import RAW.",
            )
            return
        noun = "JPG" if all(Path(path).suffix.casefold() in (".jpg", ".jpeg") for path in files) else "file"
        if not messagebox.askyesno("Send Picks to Frame", send_confirm_text(len(files), noun, "Frame")):
            return
        handoff = record_select_handoff(self.source_dir or files[0].parent, files)
        if handoff is None:
            messagebox.showerror(
                NDEX_IMAGE_MANAGER_TITLE,
                "Could not write the handoff file, so the picks were not sent. "
                "Check that %LOCALAPPDATA%\\NDEX is writable.",
            )
            return
        launched = launch_app("frame", ["--open", "--handoff", str(handoff)])
        if not launched:
            messagebox.showerror(
                NDEX_IMAGE_MANAGER_TITLE,
                "Could not find NDEX Frame. Build or install it first.",
            )

    def open_job_results(self) -> None:
        """Show what recent picks sent to Frame and backups actually did."""
        from ndex_common.report_dialog import open_job_reports

        open_job_reports(self, title=NDEX_IMAGE_MANAGER_TITLE, apps=("image_manager",))

    def open_export_dialog(self) -> None:
        if not self._can_start_work():
            return
        rows = self.selected_records()
        if not rows:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Select one or more images first.")
            return
        if self.combine_pairs.get():
            # A combined row stands for its whole shot: export every file of it.
            shots = self._shots_of(rows)
            records = shot_files(shots)
            heading = f"Export {plural(len(shots), 'selected shot')} ({file_counts_text(records)})"
        else:
            records = rows
            heading = f"Export {len(records)} selected image(s)"

        dialog = tk.Toplevel(self)
        dialog.title("Export Selected Images")
        dialog.resizable(False, False)
        dialog.configure(bg=APP_BG)
        dialog.transient(self)
        dialog.grab_set()

        destination = tk.StringVar(value="")
        pattern = tk.StringVar(value="{date}_{index}_{name}")
        start_index = tk.StringVar(value="1")
        duplicate_policy = tk.StringVar(value="rename")

        body = ttk.Frame(dialog, padding=16, style="Card.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            body,
            text=heading,
            style="Card.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 12))

        ttk.Label(body, text="Destination", style="CardMuted.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=destination, width=54).grid(row=1, column=1, sticky=tk.EW, padx=(8, 6))
        ttk.Button(
            body,
            text="Browse",
            command=lambda: self._choose_export_destination(destination),
        ).grid(row=1, column=2, sticky=tk.EW)

        ttk.Label(body, text="Rename pattern", style="CardMuted.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=pattern, width=54).grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=(8, 0))

        ttk.Label(body, text="Start index", style="CardMuted.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        ttk.Spinbox(body, from_=1, to=99999, textvariable=start_index, width=10).grid(row=3, column=1, sticky=tk.W, padx=(8, 0))

        ttk.Label(body, text="Duplicate", style="CardMuted.TLabel").grid(row=4, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(
            body,
            textvariable=duplicate_policy,
            values=("rename", "skip", "overwrite"),
            width=12,
            state="readonly",
        ).grid(row=4, column=1, sticky=tk.W, padx=(8, 0))

        help_text = (
            "Tokens: {date}, {time}, {index}, {index4}, {name}, {rating}, {pick}, {ext}\n"
            "Example: NDEX_{date}_{index}_{name}"
        )
        ttk.Label(body, text=help_text, style="CardMuted.TLabel").grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=(10, 4))

        button_row = ttk.Frame(body, style="CardInner.TFrame")
        button_row.grid(row=6, column=0, columnspan=3, sticky=tk.E, pady=(12, 0))
        ttk.Button(button_row, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        ttk.Button(
            button_row,
            text="Export",
            style="Accent.TButton",
            command=lambda: self._run_export(
                dialog,
                records,
                destination.get(),
                pattern.get(),
                start_index.get(),
                duplicate_policy.get(),
            ),
        ).pack(side=tk.RIGHT, padx=(0, 8))

        body.columnconfigure(1, weight=1)

    def _choose_export_destination(self, destination: tk.StringVar) -> None:
        selected = filedialog.askdirectory(title="Choose export destination")
        if selected:
            destination.set(selected)

    def _run_export(
        self,
        dialog: tk.Toplevel,
        records: list[ImageRecord],
        destination: str,
        pattern: str,
        start_index: int,
        duplicate_policy: str,
    ) -> None:
        if not self._can_start_work():
            return
        if not destination:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Choose an export destination.")
            return
        try:
            safe_start_index = max(1, int(start_index))
        except (TypeError, ValueError):
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Start index must be a number.")
            return
        options = ExportOptions(
            destination_dir=Path(destination),
            rename_pattern=pattern,
            start_index=safe_start_index,
            duplicate_policy=duplicate_policy,  # type: ignore[arg-type]
        )
        self._start_operation("export", records, options.destination_dir, options)
        dialog.destroy()

    def _restore_selection_ids(self, image_ids: list[int], focus_id: int) -> None:
        iids = [str(image_id) for image_id in image_ids if self.tree.exists(str(image_id))]
        if not iids:
            return
        self.tree.selection_set(iids)
        focus = str(focus_id) if str(focus_id) in iids else iids[0]
        self.tree.focus(focus)
        self.tree.see(focus)
        self.on_select()

    def _restore_selection(self, image_id: int) -> None:
        iid = str(image_id)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            self.on_select()

    def apply_layout_preset(self) -> None:
        mode = self.image_layout.get()
        panes = set(self.paned.panes())
        left_present = str(self.left_pane) in panes

        if mode == "Full":
            if left_present:
                self.paned.forget(self.left_pane)
            if self.details_frame.winfo_manager():
                self.details_frame.pack_forget()
        else:
            if not left_present:
                self.paned.insert(0, self.left_pane, weight=1)
            if not self.details_frame.winfo_manager():
                self.details_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(1, 0))
            self.after(50, self._position_sash_for_layout)

        self.after(80, lambda: self._show_preview(self.current_record))

    def apply_preview_background(self) -> None:
        color = self._preview_background_color()
        self.preview_frame.configure(bg=color)
        self.preview_label.configure(bg=color)
        self._show_preview(self.current_record)

    def _preview_background_color(self) -> str:
        return PREVIEW_BACKGROUNDS.get(self.preview_background.get(), PREVIEW_BACKGROUNDS["Dark Gray"])

    def _position_sash_for_layout(self) -> None:
        if len(self.paned.panes()) < 2:
            return
        width = max(self.paned.winfo_width(), 1)
        image_fraction = 0.8 if self.image_layout.get() == "80%" else 0.5
        left_width = int(width * (1 - image_fraction))
        if self.image_layout.get() == "50%":
            # Never clip the list columns; the preview gives way instead.
            left_width = max(left_width, min(self._list_needed_width(), int(width * 0.72)))
        self.paned.sashpos(0, max(220, left_width))

    def open_fullscreen_viewer(self) -> None:
        record = self.current_record
        if not record:
            return

        viewer = tk.Toplevel(self)
        viewer.title(self._row_title(record))
        fullscreen_bg = self._preview_background_color()
        fullscreen_fg = "#111827" if self.preview_background.get() == "Light Gray" else "#d7dee8"
        fullscreen_muted = "#374151" if self.preview_background.get() == "Light Gray" else "#9fb0c4"
        viewer.configure(bg=fullscreen_bg)
        viewer.attributes("-fullscreen", True)

        top_bar = tk.Frame(viewer, bg=fullscreen_bg, bd=0, highlightthickness=0)
        top_bar.pack(fill=tk.X, padx=14, pady=(8, 0))
        counter_label = tk.Label(
            top_bar, bg=fullscreen_bg, fg=fullscreen_fg, font=("Segoe UI", 12, "bold"),
            bd=0, highlightthickness=0,
        )
        counter_label.pack(side=tk.LEFT)
        badge_label = tk.Label(
            top_bar, font=("Segoe UI", 12, "bold"), fg="#ffffff", padx=12, pady=3,
            bd=0, highlightthickness=0,
        )
        badge_label.pack(side=tk.RIGHT)

        image_label = tk.Label(
            viewer,
            bg=fullscreen_bg,
            fg=fullscreen_fg,
            compound=tk.TOP,
            bd=0,
            highlightthickness=0,
        )
        image_label.pack(fill=tk.BOTH, expand=True)

        overlay = tk.Frame(viewer, bg=fullscreen_bg, bd=0, highlightthickness=0)
        overlay.pack(fill=tk.X)

        metadata_label = tk.Label(
            overlay,
            bg=fullscreen_bg,
            fg=fullscreen_fg,
            font=("Segoe UI", 10),
            justify=tk.LEFT,
            anchor=tk.W,
            padx=14,
            pady=4,
            bd=0,
            highlightthickness=0,
        )
        metadata_label.pack(fill=tk.X)

        controls = tk.Frame(overlay, bg=fullscreen_bg, bd=0, highlightthickness=0)
        controls.pack(fill=tk.X, padx=12, pady=(0, 8))

        tk.Button(controls, text="Previous", command=lambda: navigate(-1), width=10).pack(side=tk.LEFT)
        tk.Button(controls, text="Next", command=lambda: navigate(1), width=10).pack(side=tk.LEFT, padx=(6, 14))
        tk.Label(
            controls,
            text="Rating",
            bg=fullscreen_bg,
            fg=fullscreen_muted,
            bd=0,
            highlightthickness=0,
        ).pack(side=tk.LEFT, padx=(0, 6))

        fullscreen_stars: list[tk.Label] = []
        for rating in range(1, 6):
            star = tk.Label(
                controls,
                text=STAR_EMPTY,
                bg=fullscreen_bg,
                fg="#6b7280",
                font=("Segoe UI Symbol", 18),
                cursor="hand2",
                padx=2,
            )
            star.pack(side=tk.LEFT)
            star.bind("<Button-1>", lambda event, value=rating: set_fullscreen_rating(value, False))
            fullscreen_stars.append(star)

        tk.Button(controls, text="Clear", command=lambda: set_fullscreen_rating(0, False), width=8).pack(side=tk.LEFT, padx=(8, 18))
        tk.Label(
            controls,
            text="\u2190/\u2192 move   0\u20135 rating   P/M/X/U pick   Esc/F/double-click close",
            bg=fullscreen_bg,
            fg=fullscreen_muted,
            anchor=tk.W,
            bd=0,
            highlightthickness=0,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        def render(_event=None) -> None:
            current = self.current_record
            if not current:
                return
            image_path = current.display_source or current.thumbnail_path
            viewer.title(self._row_title(current))
            metadata_label.configure(text=self._fullscreen_detail_text(current))
            current_shot = self._shot_of(current)
            _refresh_star_labels(fullscreen_stars, current_shot.rating)
            position = next((i for i, item in enumerate(self.records) if item.id == current.id), 0)
            counter_label.configure(text=position_text(position, len(self.records)))
            badge_text, badge_color = PICK_BADGES.get(current_shot.pick_status, PICK_BADGES["Unrated"])
            badge_label.configure(text=badge_text, bg=badge_color)
            if not image_path or not image_path.exists():
                image_label.configure(image="", text=preview_unavailable_text(current))
                return
            try:
                with Image.open(image_path) as image:
                    image = ImageOps.exif_transpose(image)
                    max_size = (max(viewer.winfo_width(), 64), max(viewer.winfo_height() - 140, 64))
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                    self.fullscreen_image = ImageTk.PhotoImage(image)
                    image_label.configure(image=self.fullscreen_image, text=self._row_title(current))
            except OSError:
                image_label.configure(image="", text=preview_unavailable_text(current))

        def navigate(offset: int) -> None:
            if not self.records or not self.current_record:
                return
            current_id = self.current_record.id
            current_index = next(
                (index for index, item in enumerate(self.records) if item.id == current_id),
                0,
            )
            next_index = max(0, min(len(self.records) - 1, current_index + offset))
            next_record = self.records[next_index]
            if next_record.id is None:
                return
            self._restore_selection(next_record.id)
            render()

        def set_fullscreen_rating(rating: int, advance: bool = True) -> None:
            self.set_rating(rating, advance=advance)
            render()

        def set_fullscreen_pick(pick_status: str) -> None:
            self.set_pick(pick_status)
            render()

        def close(_event=None) -> None:
            viewer.destroy()

        viewer.bind("<Configure>", render)
        viewer.bind("<Escape>", close)
        viewer.bind("<f>", close)
        viewer.bind("<F>", close)
        viewer.bind("<Left>", lambda event: navigate(-1))
        viewer.bind("<Up>", lambda event: navigate(-1))
        viewer.bind("<Prior>", lambda event: navigate(-1))
        viewer.bind("<Right>", lambda event: navigate(1))
        viewer.bind("<Down>", lambda event: navigate(1))
        viewer.bind("<Next>", lambda event: navigate(1))
        viewer.bind("<p>", lambda event: set_fullscreen_pick("Pick"))
        viewer.bind("<P>", lambda event: set_fullscreen_pick("Pick"))
        viewer.bind("<m>", lambda event: set_fullscreen_pick("Maybe"))
        viewer.bind("<M>", lambda event: set_fullscreen_pick("Maybe"))
        viewer.bind("<x>", lambda event: set_fullscreen_pick("Reject"))
        viewer.bind("<X>", lambda event: set_fullscreen_pick("Reject"))
        viewer.bind("<u>", lambda event: set_fullscreen_pick("Unrated"))
        viewer.bind("<U>", lambda event: set_fullscreen_pick("Unrated"))
        for value in range(0, 6):
            viewer.bind(str(value), lambda event, rating=value: set_fullscreen_rating(rating))
        viewer.bind("<Double-Button-1>", close)
        viewer.after(50, render)

    def _show_preview(self, record: ImageRecord | None) -> None:
        if not record:
            self.preview_label.configure(image="", text="No preview")
            self.preview_image = None
            self.summary_text.set("Select an image to see EXIF summary.")
            return
        image_path = record.display_source or record.thumbnail_path
        if not image_path or not image_path.exists():
            self.preview_label.configure(image="", text=preview_unavailable_text(record))
            self.preview_image = None
            return
        try:
            with Image.open(image_path) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail(self._preview_max_size(), Image.Resampling.LANCZOS)
                self.preview_image = ImageTk.PhotoImage(image)
                self.preview_label.configure(image=self.preview_image, text="")
        except OSError:
            self.preview_label.configure(image="", text=preview_unavailable_text(record))
            self.preview_image = None

    def _preview_max_size(self) -> tuple[int, int]:
        width = max(self.preview_label.winfo_width() - 24, 64)
        height = max(self.preview_label.winfo_height() - 24, 64)
        return width, height

    def _schedule_preview_refresh(self) -> None:
        if not self.current_record or self._preview_resize_job is not None:
            return
        self._preview_resize_job = self.after(120, self._refresh_preview_after_resize)

    def _refresh_preview_after_resize(self) -> None:
        self._preview_resize_job = None
        self._show_preview(self.current_record)

    def _show_details(self, record: ImageRecord | None) -> None:
        self.detail_text.configure(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        if record:
            self.summary_text.set(self._summary_line(record))
            lines = self._simple_detail_lines(record)
            if self.detail_mode.get() == "Full":
                lines = self._full_detail_lines(record)
            self.detail_text.insert("1.0", "\n".join(lines))
        else:
            self.summary_text.set("Select an image to see EXIF summary.")
        self.detail_text.configure(state=tk.DISABLED)

    def _row_title(self, record: ImageRecord) -> str:
        if self.combine_pairs.get():
            shot = self._shot_of(record)
            return f"{shot.stem} ({shot.type_label})" if len(shot.records) > 1 else record.display_name
        return record.display_name

    def _file_lines(self, record: ImageRecord) -> list[str]:
        shot = self._shot_of(record)
        if self.combine_pairs.get() and len(shot.records) > 1:
            return [f"Files: {' + '.join(shot.file_names)}"]
        return [f"File: {record.display_name}"]

    def _simple_detail_lines(self, record: ImageRecord) -> list[str]:
        shot = self._shot_of(record)
        return [
            *self._file_lines(record),
            f"Capture: {record.effective_datetime:%Y-%m-%d %H:%M:%S}",
            f"Camera: {record.camera_model or '-'}",
            f"Lens: {record.lens_model or '-'}",
            f"Exposure: {record.exposure_time or '-'} / f/{record.aperture or '-'} / ISO {record.iso or '-'}",
            f"Selection: {shot.pick_status} / Rating: {_rating_text(shot.rating)}",
        ]

    def _full_detail_lines(self, record: ImageRecord) -> list[str]:
        shot = self._shot_of(record)
        combined = self.combine_pairs.get() and len(shot.records) > 1
        paths = [f"Path: {member.file_path}" for member in shot.records] if combined else [f"Path: {record.file_path}"]
        sizes = (
            [f"Files: {', '.join(f'{m.type_label} {m.file_size or chr(45)}' for m in shot.records)}"]
            if combined else []
        )
        return [
                *paths,
                *sizes,
                f"Capture: {record.effective_datetime:%Y-%m-%d %H:%M:%S}",
                f"Modified: {record.file_modified_datetime:%Y-%m-%d %H:%M:%S}",
                f"Camera: {record.camera_model or '-'}",
                f"Lens: {record.lens_model or '-'}",
                f"Focal length: {record.focal_length or '-'}",
                f"Exposure: {record.exposure_time or '-'} / f/{record.aperture or '-'} / ISO {record.iso or '-'}",
                f"Exposure compensation: {record.exposure_compensation or '-'}",
                f"White balance: {record.white_balance or '-'}",
                f"Size: {record.width or '-'} x {record.height or '-'} / {record.file_size or '-'}",
                f"Color: {record.color_space or '-'} / GPS: {record.gps or '-'}",
                f"Pair: {record.pair_status} / Proxy: {record.proxy_status}",
                f"Backup: {record.backup_status}",
                f"Selection: {shot.pick_status} / Rating: {_rating_text(shot.rating)}",
                f"Note: {record.note or '-'}",
        ]

    def _fullscreen_detail_text(self, record: ImageRecord) -> str:
        shot = self._shot_of(record)
        return (
            f"{self._row_title(record)}   {_rating_text(shot.rating)}   {shot.pick_status}\n"
            f"{self._summary_line(record)}"
        )

    def _summary_line(self, record: ImageRecord) -> str:
        return (
            f"{record.camera_model or '-'} | {record.lens_model or '-'} | "
            f"f/{record.aperture or '-'} | {record.exposure_time or '-'} | "
            f"ISO {record.iso or '-'} | {_resolution_text(record)}"
        )

    def _refresh_rating_widgets(self, rating: int) -> None:
        _refresh_star_labels(self.star_labels, rating)


def _rating_text(rating: int) -> str:
    return "none" if rating <= 0 else STAR_FILLED * rating


def _resolution_text(record: ImageRecord) -> str:
    if record.width and record.height:
        return f"{record.width} x {record.height}"
    return "resolution -"


def _refresh_star_labels(labels: list[tk.Label], rating: int) -> None:
    for index, star in enumerate(labels, start=1):
        star.configure(text=STAR_FILLED if index <= rating else STAR_EMPTY, fg=STAR if index <= rating else "#6b7280")


def run_app(initial_source: Path | None = None) -> None:
    app = ImageManagerApp(initial_source=initial_source)
    app.mainloop()
