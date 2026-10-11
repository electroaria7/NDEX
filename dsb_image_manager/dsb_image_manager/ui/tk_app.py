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
from ..services.cache import CacheManager
from ..services.catalog import Catalog
from ..services.exporter import ExportService
from ..services.scanner import ImageScanner, ScanCancelled
from ..services.thumbnails import ThumbnailLoader
from ..services.xmp_export import XmpExportService
from . import grid_model
from .thumb_grid import ThumbnailGrid, TileInfo

from ndex_common.i18n import _, ngettext
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

STAR_FILLED = "★"
STAR_EMPTY = "☆"
SORT_ASC = "↑"
SORT_DESC = "↓"
# Internal ids (also the keys stored in tk variables); display text comes from background_label().
PREVIEW_BACKGROUNDS = {
    "50% Gray": "#808080",
    "Dark Gray": "#1f2933",
    "Light Gray": "#d1d5db",
}
VIEW_MODES = ("list", "grid")
# Column headings are translated when the list is built (see _column_label).
TREE_COLUMNS = {
    "state": {"label": "", "sort_key": "pick_status", "width": 24, "minwidth": 24, "stretch": False,
              "anchor": "center", "indicator": False},
    "name": {"label": "File", "sort_key": "file_name", "width": 120, "minwidth": 84, "stretch": True},
    "type": {"label": "Type", "sort_key": "media_type", "width": 42, "minwidth": 42, "stretch": False},
    "pick": {"label": "Pick", "sort_key": "pick_status", "width": 48, "minwidth": 48, "stretch": False},
    "rating": {"label": "★", "sort_key": "rating", "width": 64, "minwidth": 64, "stretch": False},
    "date": {"label": "Date", "sort_key": "capture_datetime", "width": 64, "minwidth": 64, "stretch": False},
}
# Tints are a second cue only; the first column carries the pick glyph.
PICK_TINTS = {"Pick": "#d2efd5", "Maybe": "#ffeeb0", "Reject": "#f8cfcf"}
PICK_BADGE_COLORS = {"Pick": "#15803d", "Maybe": "#b45309", "Reject": "#b91c1c", "Unrated": "#4b5563"}
# Sorting by these columns changes row order when a mark changes.
RESORT_KEYS = ("pick_status", "rating")
# Keys must stay editable/usable inside these widgets, so arrows are not hijacked.
TEXT_INPUT_CLASSES = frozenset({"TCombobox", "TEntry", "Entry", "TSpinbox", "Spinbox", "Text"})


def column_label(column: str) -> str:
    """Translated list heading for a TREE_COLUMNS id."""
    if column == "name":
        return _("File")
    if column == "type":
        return _("Type")
    if column == "pick":
        return _("Pick")
    if column == "date":
        return _("Date")
    return TREE_COLUMNS[column]["label"]


def file_filter_options():
    """(internal key, display label) pairs; code only ever compares the keys."""
    return (
        ("all", _("All files")),
        ("paired", _("Pairs (RAW+JPG)")),
        ("raw", _("RAW only")),
        ("jpg", _("JPG only")),
        ("raw_only", _("Unpaired RAW")),
        ("jpg_only", _("Unpaired JPG")),
        ("proxy_failed", _("Preview failed")),
    )


def pick_filter_options():
    return (
        ("all", _("Any pick state")),
        ("Unrated", _("Unrated")),
        ("Pick", _("Pick")),
        ("Maybe", _("Maybe")),
        ("Reject", _("Reject")),
    )


def rating_filter_options():
    return (
        ("0", _("Any rating")),
        ("1", _("1★+")),
        ("3", _("3★+")),
        ("5", _("5★")),
    )


def background_label(key: str) -> str:
    return {
        "50% Gray": _("50% Gray"),
        "Dark Gray": _("Dark Gray"),
        "Light Gray": _("Light Gray"),
    }.get(key, key)


def pick_label(status: str) -> str:
    """Display text of an internal pick state."""
    return {
        "Pick": _("Pick"),
        "Maybe": _("Maybe"),
        "Reject": _("Reject"),
        "Unrated": _("Unrated"),
    }.get(status, status)


def pick_badge(status: str) -> tuple[str, str]:
    """Fullscreen badge text and colour for an internal pick state."""
    text = {
        "Pick": _("✓ PICK"),
        "Maybe": _("? MAYBE"),
        "Reject": _("✕ REJECT"),
    }.get(status, _("UNRATED"))
    return text, PICK_BADGE_COLORS.get(status, PICK_BADGE_COLORS["Unrated"])


def kind_name(kind: str) -> str:
    return {
        "scan": _("Scan"),
        "backup": _("Backup"),
        "export": _("Export"),
        "xmp": _("XMP sidecars"),
    }.get(kind, kind.title())


def shortcut_hint() -> str:
    return _("P Pick · X Reject · M Maybe · U Clear · 0–5 Stars · "
             "←/→ Move · F Full screen · Ctrl+Z Undo")


def label_for(options, value: str) -> str:
    return next((label for key, label in options if key == value), options[0][1])


def value_for(options, label: str) -> str:
    return next((key for key, text in options if text == label), options[0][0])


# ---- counted phrases (singular/plural handled by ngettext) ----

def file_count(count: int) -> str:
    return ngettext("{count} file", "{count} files", count).format(count=count)


def shot_count(count: int) -> str:
    return ngettext("{count} shot", "{count} shots", count).format(count=count)


def error_count(count: int) -> str:
    return ngettext("{count} error", "{count} errors", count).format(count=count)


def image_count(count: int) -> str:
    return ngettext("{count} image", "{count} images", count).format(count=count)


def sidecar_count(count: int) -> str:
    return ngettext("{count} XMP sidecar", "{count} XMP sidecars", count).format(count=count)


def picked_shot_count(count: int) -> str:
    return ngettext("{count} picked shot", "{count} picked shots", count).format(count=count)


def picked_jpg_count(count: int) -> str:
    return ngettext("{count} picked JPG", "{count} picked JPGs", count).format(count=count)


def selected_shot_count(count: int) -> str:
    return ngettext("{count} selected shot", "{count} selected shots", count).format(count=count)


def unit_count(count: int, noun: str) -> str:
    """Rows are shots when RAW+JPG are combined, files otherwise."""
    return shot_count(count) if noun == "shot" else file_count(count)


def record_matches_filters(record: ImageRecord, pick_filter: str, min_rating: int) -> bool:
    """Pick and rating part of the list filters (file-type filters never change on a mark)."""
    if pick_filter != "all" and record.pick_status != pick_filter:
        return False
    return record.rating >= min_rating


def progress_text(kind: str, index: int, total: int, name: str) -> str:
    template = {
        "scan": _("Scanning {index}/{total} — {name}"),
        "backup": _("Backing up {index}/{total} — {name}"),
        "export": _("Exporting {index}/{total} — {name}"),
        "xmp": _("Writing XMP {index}/{total} — {name}"),
    }.get(kind)
    if template is None:
        return f"{kind.title()} {index}/{total} — {name}"
    return template.format(index=index, total=total, name=name)


def ready_status_text(total_files: int, shot_total: int) -> str:
    return _("Ready. {files} ({shots})").format(files=file_count(total_files), shots=shot_count(shot_total))


def selection_status_text(selected: int, shown: int) -> str:
    text = _("{selected} selected / {shown} shown").format(selected=selected, shown=shown)
    if selected > 1:
        text = _("{text} — marks apply to all {selected}").format(text=text, selected=selected)
    return text


def position_text(index: int, total: int) -> str:
    return f"{index + 1} / {total}"


def preview_unavailable_text(record: ImageRecord) -> str:
    if record.media_type == "raw":
        if record.pair_status == "raw_jpg_pair":
            return _("No embedded preview — view the JPG of this pair instead.")
        return _("No embedded preview in this RAW file.")
    return _("Preview unavailable")


def empty_state_kind(has_catalog: bool, scanning: bool, record_count: int, filters_active: bool) -> str | None:
    if scanning:
        return None
    if not has_catalog:
        return "start"
    if record_count:
        return None
    return "filtered" if filters_active else "empty"


def send_confirm_text(count: int, noun: str, target: str) -> str:
    if noun == "JPG":
        text = ngettext("Send {count} picked JPG to {target}?", "Send {count} picked JPGs to {target}?", count)
    else:
        text = ngettext("Send {count} picked file to {target}?", "Send {count} picked files to {target}?", count)
    return text.format(count=count, target=target)


def no_jpg_text(count: int, sent: bool = False) -> str:
    """Picked shots that only have a RAW cannot be handed to JPG-only apps."""
    if sent:
        text = ngettext("{count} picked shot has no JPG and was not sent.",
                        "{count} picked shots have no JPG and were not sent.", count)
    else:
        text = ngettext("{count} picked shot has no JPG and will not be sent.",
                        "{count} picked shots have no JPG and will not be sent.", count)
    return text.format(count=count)


def file_counts_text(files) -> str:
    """'6 JPG + 6 RAW' for a list of file records."""
    files = list(files)
    jpg = sum(1 for record in files if record.media_type == "jpg")
    raw = sum(1 for record in files if record.media_type == "raw")
    other = len(files) - jpg - raw
    parts = [_("{count} JPG").format(count=jpg)] if jpg else []
    parts += [_("{count} RAW").format(count=raw)] if raw else []
    parts += [_("{count} other").format(count=other)] if other else []
    return " + ".join(parts)


def shot_files(shots) -> list[ImageRecord]:
    return [record for shot in shots for record in shot.records]


def backup_confirm_text(shots, destination) -> str:
    shots = list(shots)
    return _("Back up {shots} ({files}) to:\n{destination}?").format(
        shots=picked_shot_count(len(shots)), files=file_counts_text(shot_files(shots)), destination=destination)


def pick_change_label(status: str) -> str:
    return {
        "Pick": _("Pick"),
        "Maybe": _("Maybe"),
        "Reject": _("Reject"),
        "Unrated": _("Clear pick"),
    }.get(status, status)


def mark_change_label(pick_status, rating, count: int, noun: str) -> str:
    """Edit-menu wording: 'Pick: Reject 12 shots' or 'Rating: 3★ 1 shot'."""
    if pick_status is not None:
        what = _("Pick: {label}").format(label=pick_change_label(pick_status))
    else:
        what = _("Rating: {stars}").format(stars=f"{rating}{STAR_FILLED}" if rating else _("Clear"))
    return _("{what} {subject}").format(what=what, subject=unit_count(count, noun))


def mark_done_text(pick_status, rating, count: int, noun: str) -> str:
    subject = unit_count(count, noun)
    if pick_status is not None:
        template = {
            "Pick": _("Picked {subject}"),
            "Maybe": _("Marked Maybe {subject}"),
            "Reject": _("Rejected {subject}"),
            "Unrated": _("Cleared pick on {subject}"),
        }.get(pick_status, "{subject}")
        return template.format(subject=subject)
    if rating:
        return _("Rated {subject} {stars}").format(subject=subject, stars=f"{rating}{STAR_FILLED}")
    return _("Cleared rating on {subject}").format(subject=subject)


def scan_stopped_text(listed: int, total: int) -> str:
    if total <= 0:
        return _("Scan stopped before any files were listed. The previous catalog was kept.")
    return _("Scan stopped — {listed} of {total} files listed. Rescan (F5) to finish.").format(
        listed=listed, total=total)


def operation_summary_text(kind: str, summary, destination) -> str:
    if kind == "backup":
        done = file_count(getattr(summary, "copied", 0))
    elif kind == "export":
        done = file_count(getattr(summary, "exported", 0))
    else:
        done = sidecar_count(getattr(summary, "written", 0))
    if summary.cancelled:
        head = {
            "backup": _("Backup cancelled after {done}"),
            "export": _("Export cancelled after {done}"),
            "xmp": _("XMP export cancelled after {done}"),
        }.get(kind, _("Cancelled after {done}")).format(done=done)
        tail = _("({skipped} skipped, {not_run} not run or failed)").format(
            skipped=summary.skipped, not_run=summary.errors)
    else:
        head = {
            "backup": _("Backed up {done}"),
            "export": _("Exported {done}"),
            "xmp": _("Wrote {done}"),
        }.get(kind, _("Completed {done}")).format(done=done)
        tail = _("({skipped} skipped, {errors})").format(skipped=summary.skipped, errors=error_count(summary.errors))
    if destination:
        if kind in ("backup", "export"):
            head = _("{head} to {destination}").format(head=head, destination=destination)
        else:
            head = _("{head} next to the photos in {destination}").format(head=head, destination=destination)
    return f"{head} {tail}"


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

        try:
            stored_view = get_section(SETTINGS_SECTION)
        except OSError:
            stored_view = {}
        view_mode = stored_view.get("view_mode", "list")
        grid_size = stored_view.get("grid_size", grid_model.DEFAULT_TILE_SIZE)
        self.view_mode = tk.StringVar(value=view_mode if view_mode in VIEW_MODES else "list")
        self.grid_size = tk.StringVar(value=grid_size if grid_size in grid_model.TILE_SIZES else grid_model.DEFAULT_TILE_SIZE)
        self.grid_view: ThumbnailGrid | None = None
        self._cache_manager: CacheManager | None = None
        self._grid_anchor: str | None = None
        self._compact = False

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
        self.status = tk.StringVar(value=_("Choose a shooting folder to start culling."))
        self.selection_status = tk.StringVar(value=_("{count} selected").format(count=0))
        self.folder_status = tk.StringVar(value=_("No folder selected"))
        self.catalog_status = tk.StringVar(value=_("{count} shown").format(count=0))
        self.summary_text = tk.StringVar(value=_("Select an image to see EXIF summary."))

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
                _("Handoff folder does not exist:\n{folder}").format(folder=source_dir),
            )
            return
        self.source_dir = source_dir
        self.folder_status.set(source_dir.name)
        self._remember_last_folder()
        self.scan_folder()

    @staticmethod
    def _hint(name: str) -> str:
        """Full description of a workflow action (menu status bar and toolbar tooltips)."""
        return {
            "export": _("Copy the selected photos to a folder with a rename pattern."),
            "backup": _("Copy every file of the picked shots (RAW and JPG) to a backup folder and verify the copies."),
            "xmp": _("Write .xmp files next to the photos with their star ratings and pick flags."),
            "selector": _("Open the picked JPGs in Auto Selector."),
            "frame": _("Open the picked JPG/PNG/TIFF files in Frame."),
        }[name]

    def _build_filter_menu(self, parent) -> tk.Menu:
        """Filter choices for the menu bar and for the toolbar's collapsed Filter button."""
        filter_menu = tk.Menu(parent, tearoff=0)
        for title, options, variable in (
            (_("Type"), file_filter_options(), self.file_filter),
            (_("Pick"), pick_filter_options(), self.pick_filter),
            (_("Rating"), rating_filter_options(), self.rating_filter),
        ):
            submenu = tk.Menu(filter_menu, tearoff=0)
            for value, label in options:
                submenu.add_radiobutton(label=label, variable=variable, value=value, command=self.refresh_records)
            filter_menu.add_cascade(label=title, menu=submenu)
        filter_menu.add_separator()
        filter_menu.add_command(label=_("Clear Filters"), command=self.clear_filters)
        return filter_menu

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=0)
        busy_actions: list[int] = []
        self._menu_hints: dict[int, str] = {}

        def add_action(label: str, command, accelerator: str | None = None, busy_sensitive: bool = True,
                       hint: str = "") -> None:
            options = {"label": label, "command": command}
            if accelerator:
                options["accelerator"] = accelerator
            file_menu.add_command(**options)
            index = file_menu.index("end")
            if busy_sensitive:
                busy_actions.append(index)
            if hint:
                self._menu_hints[index] = hint

        add_action(_("Choose Folder…"), self.choose_folder, "Ctrl+O")
        add_action(_("Reopen Last Folder"), self.reopen_last_folder)
        add_action(_("Rescan"), self.rescan, "F5")
        file_menu.add_separator()
        add_action(_("Export Selected…"), self.open_export_dialog, "Ctrl+E", hint=self._hint("export"))
        add_action(_("Backup Picked…"), self.backup_picked, hint=self._hint("backup"))
        add_action(_("Write XMP Sidecars (for Lightroom/Evoto)"), self.export_xmp_sidecars, hint=self._hint("xmp"))
        add_action(_("Send Picks to Auto Selector"), self.send_to_auto_selector, hint=self._hint("selector"))
        add_action(_("Send Picks to Frame"), self.send_picks_to_frame, hint=self._hint("frame"))
        file_menu.add_separator()
        add_action(_("Job Results…"), self.open_job_results, busy_sensitive=False)
        file_menu.add_separator()
        add_action(_("Exit"), self.destroy, busy_sensitive=False)
        self.file_menu = file_menu
        self._file_action_indices = busy_actions
        file_menu.bind("<<MenuSelect>>", self._on_file_menu_select)
        menu_bar.add_cascade(label=_("File"), menu=file_menu)

        edit_menu = tk.Menu(menu_bar, tearoff=0, postcommand=self._update_undo_menu)
        edit_menu.add_command(label=_("Undo"), accelerator="Ctrl+Z", command=self.undo, state=tk.DISABLED)
        edit_menu.add_command(label=_("Redo"), accelerator="Ctrl+Y", command=self.redo, state=tk.DISABLED)
        self.edit_menu = edit_menu
        menu_bar.add_cascade(label=_("Edit"), menu=edit_menu)

        selection_menu = tk.Menu(menu_bar, tearoff=0)
        selection_menu.add_command(label=_("Select All Visible"), accelerator="Ctrl+A", command=self.select_all_visible)
        selection_menu.add_command(label=_("Full Screen Preview"), accelerator="F", command=self.open_fullscreen_viewer)
        menu_bar.add_cascade(label=_("Selection"), menu=selection_menu)

        filter_menu = self._build_filter_menu(menu_bar)
        menu_bar.add_cascade(label=_("Filter"), menu=filter_menu)

        view_menu = tk.Menu(menu_bar, tearoff=0)
        view_menu.add_radiobutton(label=_("List"), variable=self.view_mode, value="list",
                                  command=self.apply_view_mode)
        view_menu.add_radiobutton(label=_("Grid"), variable=self.view_mode, value="grid", accelerator="G",
                                  command=self.apply_view_mode)
        size_menu = tk.Menu(view_menu, tearoff=0)
        for value, label in (("small", _("Small")), ("medium", _("Medium")), ("large", _("Large"))):
            size_menu.add_radiobutton(label=label, variable=self.grid_size, value=value,
                                      command=self.apply_grid_size)
        view_menu.add_cascade(label=_("Thumbnail Size"), menu=size_menu)
        view_menu.add_separator()
        exif_menu = tk.Menu(view_menu, tearoff=0)
        for value, label in (("Simple", _("Simple")), ("Full", _("Full"))):
            exif_menu.add_radiobutton(
                label=label,
                variable=self.detail_mode,
                value=value,
                command=lambda: self._show_details(self.current_record),
            )
        layout_menu = tk.Menu(view_menu, tearoff=0)
        for value, label in (("50%", "50%"), ("80%", "80%"), ("Full", _("Full"))):
            layout_menu.add_radiobutton(
                label=label,
                variable=self.image_layout,
                value=value,
                command=self.apply_layout_preset,
            )
        background_menu = tk.Menu(view_menu, tearoff=0)
        for value in PREVIEW_BACKGROUNDS:
            background_menu.add_radiobutton(
                label=background_label(value),
                variable=self.preview_background,
                value=value,
                command=self.apply_preview_background,
            )
        view_menu.add_cascade(label=_("EXIF Detail"), menu=exif_menu)
        view_menu.add_cascade(label=_("Image Layout"), menu=layout_menu)
        view_menu.add_cascade(label=_("Preview Background"), menu=background_menu)
        view_menu.add_separator()
        view_menu.add_checkbutton(
            label=_("Show RAW+JPG as one row"),
            variable=self.combine_pairs,
            command=self._on_combine_toggled,
        )
        view_menu.add_checkbutton(
            label=_("Advance after Pick/Reject/Rating"),
            variable=self.advance_after_mark,
            command=self._save_advance_setting,
        )
        menu_bar.add_cascade(label=_("View"), menu=view_menu)

        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(label=_("Shortcuts"), command=self.show_shortcuts)
        menu_bar.add_cascade(label=_("Help"), menu=help_menu)

        self.configure(menu=menu_bar)

    def _build_ui(self) -> None:
        header = build_app_header(
            self,
            title=NDEX_IMAGE_MANAGER_TITLE,
            tagline=_("Browse, rate, select, and export"),
            holder=self.brand_images,
        )
        header.pack(fill=tk.X)
        self.header = header
        self._tagline = (header.grid_slaves(row=1, column=0) or [None])[0]
        info = ttk.Frame(header, style="Header.TFrame")
        info.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))
        folder_label = ttk.Label(info, textvariable=self.folder_status, style="Muted.TLabel", width=26, anchor="e")
        folder_label.pack(anchor=tk.E)
        Tooltip(folder_label, lambda: str(self.source_dir) if self.source_dir else self.folder_status.get())
        ttk.Label(info, textvariable=self.catalog_status, style="Muted.TLabel", width=26, anchor="e").pack(anchor=tk.E)

        toolbar_outer = ttk.Frame(self, padding=(16, 0, 16, 10))
        toolbar_outer.pack(fill=tk.X)
        # One card holds folder + filters, marks and workflow actions on a single row;
        # the workflow group drops to a second row only when the window is too narrow.
        toolbar = ttk.Frame(toolbar_outer, padding=(10, 8), style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X)
        self.actions_toolbar = toolbar
        toolbar.columnconfigure(2, weight=1)

        self.filter_actions = ttk.Frame(toolbar, style="Toolbar.TFrame")
        self.filter_actions.grid(row=0, column=0, sticky="w")
        ttk.Style(self).configure("Compact.TButton", padding=(6, 4))
        self.choose_button = ttk.Button(self.filter_actions, text=_("Folder\u2026"), width=0,
                                        style="Compact.TButton", command=self.choose_folder)
        self.choose_button.pack(side=tk.LEFT, padx=(0, 8))
        Tooltip(self.choose_button, _("Choose a shooting folder to scan (Ctrl+O)."))

        file_filter = self._filter_combo(self.file_filter_label, file_filter_options(), self.file_filter)
        self.file_filter_widget = file_filter
        pick_filter = self._filter_combo(self.pick_filter_label, pick_filter_options(), self.pick_filter)
        self.pick_filter_widget = pick_filter
        rating_filter = self._filter_combo(self.rating_filter_label, rating_filter_options(), self.rating_filter)
        self.rating_filter_widget = rating_filter
        self._filter_combos = [file_filter, pick_filter, rating_filter]
        # Narrow windows swap the three combos for one button that opens the same choices.
        self.filter_button = ttk.Button(self.filter_actions, style="Compact.TButton", width=0,
                                        command=self._post_filter_menu)
        self._filter_popup = self._build_filter_menu(self.filter_button)
        Tooltip(self.filter_button, _("Filter the list by file type, pick state and rating."))
        self._update_filter_button()
        Tooltip(file_filter, _("Show only photos of this file type."))
        Tooltip(pick_filter, _("Show only photos with this pick state."))
        Tooltip(rating_filter, _("Show only photos with at least this star rating."))

        self._build_culling_actions(toolbar)

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
            self.tree.heading(column, text=column_label(column), command=lambda name=column: self.sort_by_column(name))
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
        self.tree_scrollbar = scrollbar
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        for pick_status, tint in PICK_TINTS.items():
            self.tree.tag_configure(pick_status, background=tint)
        # Tree-level bindings stop the Treeview class binding from moving a
        # second row; the root binding handles focus elsewhere.
        for key, offset, vertical in (("Up", -1, True), ("Down", 1, True), ("Left", -1, False), ("Right", 1, False)):
            self.tree.bind(f"<{key}>", lambda event, step=offset, v=vertical: self._on_arrow(event, step, v))
        self.tree.bind("<Configure>", self._fit_name_column, add="+")
        self.paned.bind("<Configure>", self._ensure_list_width, add="+")
        self._build_grid()
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
            text=_("No preview"),
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
            text=_("EXIF / Selection"),
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
        ttk.Button(rating_row, text=_("Clear"), command=lambda: self.set_rating(0, advance=False)).pack(side=tk.LEFT, padx=(8, 0))

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
        self.cancel_button = ttk.Button(status_row, text=_("Cancel"), command=self.cancel_work, state=tk.DISABLED)
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
        self.hint_label = ttk.Label(bottom, text=shortcut_hint(), style="Muted.TLabel")
        self.hint_label.pack(in_=self.footer_info_row, side=tk.RIGHT)
        self._hint_below = False
        self._hint_state = "beside"
        bottom.bind("<Configure>", self._layout_footer_hint)
        self.bind("<Configure>", self._on_root_configure, add="+")
        self.after(100, self.apply_layout_preset)
        self.after(120, self.apply_preview_background)
        self._update_culling_actions()
        self.apply_view_mode(persist=False)

    def _filter_combo(self, text_var: tk.StringVar, options, key_var: tk.StringVar) -> ttk.Combobox:
        labels = [label for _value, label in options]
        combo = ttk.Combobox(
            self.filter_actions, textvariable=text_var, values=labels,
            width=max(8, min(15, max(len(label) for label in labels))), state="readonly",
        )
        combo.pack(side=tk.LEFT, padx=(0, 6))
        combo.bind("<<ComboboxSelected>>", lambda event: self._on_filter_chosen(key_var, options, combo))
        return combo

    def _build_culling_actions(self, toolbar: ttk.Frame) -> None:
        self.mark_actions = ttk.Frame(toolbar, style="Toolbar.TFrame")
        self.mark_actions.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.mark_buttons: dict[str, ttk.Button] = {}
        for status, text, tip in (
            ("Pick", _("Pick"), _("Pick (P): mark the selected photos as picks.")),
            ("Maybe", _("Maybe"), _("Maybe (M): mark the selected photos as maybe.")),
            ("Reject", _("Reject"), _("Reject (X): mark the selected photos as rejects.")),
            ("Unrated", _("Clear"), _("Clear (U): clear the pick flag for the selected photos; keep their star ratings.")),
        ):
            button = ttk.Button(
                self.mark_actions, text=text, width=0, style="Compact.TButton",
                command=lambda mark=status: self.set_pick(mark),
            )
            button.pack(side=tk.LEFT, padx=(0, 4))
            Tooltip(button, tip)
            self.mark_buttons[status] = button

        self.workflow_actions = ttk.Frame(toolbar, style="Toolbar.TFrame")
        self.workflow_actions.grid(row=0, column=3, sticky="e")
        self.export_button = ttk.Button(
            self.workflow_actions, text=_("Export\u2026"), width=0, style="Compact.TButton",
            command=self.open_export_dialog)
        self.export_button.pack(side=tk.LEFT, padx=(0, 4))
        self.send_selector_button = ttk.Button(
            self.workflow_actions, text=_("\u2192 Auto Selector"), width=0, style="Compact.TButton",
            command=self.send_to_auto_selector)
        self.send_selector_button.pack(side=tk.LEFT, padx=(0, 4))
        self.send_frame_button = ttk.Button(
            self.workflow_actions, text=_("\u2192 Frame"), width=0, style="Compact.TButton",
            command=self.send_picks_to_frame)
        self.send_frame_button.pack(side=tk.LEFT)
        for button, name in (
            (self.export_button, "export"),
            (self.send_selector_button, "selector"),
            (self.send_frame_button, "frame"),
        ):
            Tooltip(button, self._hint(name))
        self._actions_stacked = False
        self._filters_full = True
        self.actions_toolbar.bind("<Configure>", self._layout_culling_actions)

    def _update_filter_button(self) -> None:
        active = sum((self.file_filter.get() != "all", self.pick_filter.get() != "all", self._min_rating() > 0))
        self.filter_button.configure(
            text=_("Filter ({count}) \u25be").format(count=active) if active else _("Filter \u25be"))

    def _post_filter_menu(self) -> None:
        button = self.filter_button
        self._filter_popup.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())

    def _layout_culling_actions(self, event=None) -> None:
        """One toolbar row: full filter combos, else a Filter button, else workflow on a second row."""
        width = event.width if event is not None else self.actions_toolbar.winfo_width()
        gap = self._scaled(8)
        marks, workflow = self.mark_actions.winfo_reqwidth(), self.workflow_actions.winfo_reqwidth()
        folder = self.choose_button.winfo_reqwidth() + gap
        full = folder + sum(combo.winfo_reqwidth() + 6 for combo in self._filter_combos)
        collapsed = folder + self.filter_button.winfo_reqwidth()
        room = width - self._scaled(20) - self._scaled(8)  # toolbar padding and breathing space
        full_filters = room >= full + marks + workflow
        stacked = not full_filters and room < collapsed + marks + workflow
        if stacked:
            full_filters = room >= full + marks
        if full_filters != self._filters_full:
            self._filters_full = full_filters
            for combo in self._filter_combos:
                combo.pack_forget()
            self.filter_button.pack_forget()
            if full_filters:
                for combo in self._filter_combos:
                    combo.pack(side=tk.LEFT, padx=(0, 6))
            else:
                self.filter_button.pack(side=tk.LEFT, padx=(0, 6))
        if stacked != self._actions_stacked:
            self._actions_stacked = stacked
            self.workflow_actions.grid_configure(
                row=1 if stacked else 0, column=0 if stacked else 3,
                columnspan=4 if stacked else 1, sticky="w" if stacked else "e",
                pady=(6, 0) if stacked else 0,
            )

    def _on_root_configure(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        compact = self.winfo_height() < self._scaled(800)
        if compact == self._compact:
            return
        self._compact = compact
        # A short window gives its height to the photo list: no tagline, no shortcut hint.
        if self._tagline is not None:
            if compact:
                self._tagline.grid_remove()
            else:
                self._tagline.grid()
        self._layout_footer_hint()

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
        self.bind("<Down>", lambda event: self._on_arrow(event, 1, True))
        self.bind("<Right>", lambda event: self._on_arrow(event, 1))
        self.bind("<Up>", lambda event: self._on_arrow(event, -1, True))
        self.bind("<Left>", lambda event: self._on_arrow(event, -1))
        for letter in ("g", "G"):
            self.bind(f"<{letter}>", lambda event: self._on_photo_shortcut(event, self.toggle_view_mode))
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

        def fit(sample: str, header: str = "", arrow: str = "") -> int:
            # Only the sorted column carries an arrow; give Date room for it.
            header_width = head.measure(header + arrow) + pad if header else 0
            return max(body.measure(sample) + pad, header_width)

        fixed = {
            "state": body.measure("\u2715") + pad,
            "type": fit("RAW+JPG", column_label("type")),
            "pick": fit(pick_label("Unrated"), column_label("pick")),
            "rating": fit(STAR_FILLED * 5, STAR_FILLED),
            "date": fit("00-00 00:00", column_label("date"), " \u2191"),
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
        try:
            needed = self.selection_label.winfo_reqwidth() + self.hint_label.winfo_reqwidth() + 40
            fits = self.footer.winfo_width() >= needed
        except tk.TclError:
            return
        # A short window drops the hint instead of spending a row on it (Help > Shortcuts has it).
        state = "beside" if fits else ("hidden" if self._compact else "below")
        if state == self._hint_state:
            return
        self._hint_state = state
        self._hint_below = state == "below"
        self.hint_label.pack_forget()
        self.footer_hint_row.pack_forget()
        if state == "beside":
            self.hint_label.pack(in_=self.footer_info_row, side=tk.RIGHT)
        elif state == "below":
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
        self.file_filter_label.set(label_for(file_filter_options(), self.file_filter.get()))
        self.pick_filter_label.set(label_for(pick_filter_options(), self.pick_filter.get()))
        self.rating_filter_label.set(label_for(rating_filter_options(), self.rating_filter.get()))

    def _on_filter_chosen(self, variable: tk.StringVar, options, widget) -> None:
        index = widget.current()
        variable.set(options[index][0] if 0 <= index < len(options) else value_for(options, widget.get()))
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

    def _on_arrow(self, event, offset: int, vertical: bool = False):
        """Move exactly one row (one tile in the grid), unless a text-input widget owns the key."""
        widget_class = ""
        try:
            widget_class = event.widget.winfo_class()
        except (AttributeError, tk.TclError):
            pass
        state = getattr(event, "state", 0)
        if widget_class in TEXT_INPUT_CLASSES:
            return None
        if self.view_mode.get() == "grid":
            # Up/Down move by a whole row of tiles; Shift extends the selection.
            self.move_selection(offset, vertical=vertical, extend=bool(state & 0x1))
            return "break"
        # Shift/Ctrl+arrow keep their native Treeview behaviour (range select).
        if state & 0x5:
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
        except tk.TclError:
            index = None
        hint = self._menu_hints.get(index) if isinstance(index, int) else None
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
            text, button, command = (_("Choose a shooting folder to start culling"),
                                     _("Choose Folder\u2026 (Ctrl+O)"), self.choose_folder)
        elif kind == "filtered":
            text, button, command = _("No photos match these filters."), _("Clear Filters"), self.clear_filters
        else:
            text, button, command = (_("No supported photos were found in this folder."),
                                     _("Choose Another Folder\u2026"), self.choose_folder)
        self.empty_label.configure(text=text)
        self.empty_button.configure(text=button, command=command)
        host = self.grid_view if self.view_mode.get() == "grid" and self.grid_view is not None else self.tree
        self.empty_overlay.place(in_=host, x=0, y=0, relwidth=1, relheight=1)
        self.empty_overlay.lift()

    def choose_folder(self) -> None:
        if not self._can_start_work():
            return
        selected = filedialog.askdirectory(title=_("Choose a shooting folder"))
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
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("No previous folder found."))
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
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("Choose a folder first."))
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
        self.status.set(_("Scanning {folder}\u2026").format(folder=self.source_dir.name))
        self._stale_ids.clear()
        self.tree.delete(*self.tree.get_children())
        self._clear_row_model()
        self._cache_manager = None
        self._grid_anchor = None
        if self.grid_view is not None:
            self.grid_view.canvas.yview_moveto(0)
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
            self.status.set(_("A task is running. Wait for it to finish or use Cancel."))
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
        self.filter_button.configure(state=tk.DISABLED if busy else tk.NORMAL)
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
        message = _("Cancelling after the current file or metadata batch finishes...")
        self.status.set(_("Closing: {message}").format(message=message) if self._closing else message)

    def destroy(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return  # already destroyed
        if self._active_job is not None:
            self._closing = True
            self.cancel_work()
            return
        self._closing = True
        if self.catalog:
            self.catalog.close()
            self.catalog = None
        if getattr(self, "_grid_loader", None) is not None:
            self._grid_loader.close()
        if self.grid_view is not None:
            # Destroyed first so it cancels its own timers; the sweep below only knows raw Tcl ids.
            self.grid_view.destroy()
            self.grid_view = None
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
                self.status.set(_("Could not update the task view: {error}").format(error=exc))
                messagebox.showerror(NDEX_IMAGE_MANAGER_TITLE, _("Could not update the task view:\n{error}").format(error=exc))
        self._queue_job = self.after(100, self._process_ui_queue)

    def _dispatch_work_event(self, event) -> bool:
        kind = event[0]
        if kind == "scan_rows":
            _kind, _generation, catalog_path, batch = event
            self._ingest_scan_rows(catalog_path, batch)
        elif kind == "work_progress":
            _kind, _generation, index, total, name = event
            if index > 0:
                self.work_progress.stop()
                self.work_progress.configure(mode="determinate", maximum=max(total, 1), value=index)
            if not self._cancel_event.is_set():
                self.status.set(progress_text(self._active_job or "scan", index, total, name))
        elif kind == "work_done":
            _kind, _generation, task, result, error, cancelled = event
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
                        _("Closing Image Manager"),
                        _("The task finished with problems:\n\n{problems}").format(problems="\n".join(problems)),
                    )
                self.destroy()
                return False
            if error:
                self.status.set(_("{kind} failed.").format(kind=kind_name(task)))
                messagebox.showerror(_("{kind} failed").format(kind=kind_name(task)), error)
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
        return " " + _("Merged RAW and JPG marks for {shots}.").format(shots=shot_count(fixed))

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
            pick_label(shot.pick_status),
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
            self.status.set(_("No photos match these filters.") if self._filters_active() else _("No photos to show."))
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
            label = column_label(column)
            if config.get("indicator", True) and config["sort_key"] == current_sort:
                label = f"{label} {SORT_DESC if self.sort_descending.get() else SORT_ASC}"
            self.tree.heading(column, text=label, command=lambda name=column: self.sort_by_column(name))

    def update_catalog_status(self) -> None:
        folder = self.source_dir.name if self.source_dir else _("No folder selected")
        self.folder_status.set(folder)
        text = _("{count} shown").format(count=len(self.records))
        if self._filters_active():
            text = _("{text} (filtered)").format(text=text)
        self.catalog_status.set(text)
        self._update_filter_button()

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
        self._grid_sync(reveal=True)

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
                self.status.set(_("A task is running. Wait for it to finish or use Cancel."))
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
        marks = []
        for shot in shots:
            for record in shot.records:
                if record.id is None:
                    continue
                new_pick = record.pick_status if pick_status is None else pick_status
                new_rating = record.rating if rating is None else rating
                if (new_pick, new_rating) != (record.pick_status, record.rating):
                    # History is keyed by the file's path, not its catalog row id: a rescan can
                    # reuse an id for a different image.
                    entries.append((self._identity(record), record.pick_status, record.rating, new_pick, new_rating))
                    marks.append((record.id, new_pick, new_rating))
        if entries:
            self.catalog.set_marks(marks)
            self._set_memory_marks(marks)
            noun = "shot" if self.combine_pairs.get() else "file"
            self.undo_stack.push(MarkChange(mark_change_label(pick_status, rating, len(rows), noun), entries))
            self._update_undo_menu()
            if len(rows) > 1:
                self.status.set(_("{done} \u2014 Ctrl+Z to undo").format(
                    done=mark_done_text(pick_status, rating, len(rows), noun)))
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

    @staticmethod
    def _identity(record: ImageRecord) -> str:
        return str(record.file_path).casefold()

    def _update_undo_menu(self) -> None:
        if not hasattr(self, "edit_menu"):
            return
        usable = self.catalog is not None and self._can_mark()
        for index, name, template, label in (
            (0, _("Undo"), _("Undo {label}"), self.undo_stack.undo_label),
            (1, _("Redo"), _("Redo {label}"), self.undo_stack.redo_label),
        ):
            self.edit_menu.entryconfigure(
                index, label=template.format(label=label) if label else name,
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
            self.status.set(_("Nothing to redo.") if redo else _("Nothing to undo."))
            return
        by_key = {self._identity(record): record for record in self.all_records}
        states: dict[int, tuple[str, int]] = {}
        for key, old_pick, old_stars, new_pick, new_stars in change.entries:
            record = by_key.get(key)
            if record is None or record.id is None:
                continue  # that file is gone after a rescan; nothing to restore
            states[record.id] = (new_pick, new_stars) if redo else (old_pick, old_stars)
        # A file that joined a shot since the mark (a RAW found next to its JPG) takes the shot's state.
        for image_id, state in list(states.items()):
            for member in self._shot_of(self._records_by_id[image_id]).records:
                if member.id is not None and member.id not in states:
                    states[member.id] = state
        marks = [(image_id, pick, stars) for image_id, (pick, stars) in states.items()]
        if not marks:
            self.status.set(_("Nothing to redo.") if redo else _("Nothing to undo."))
            self._update_undo_menu()
            return
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
        self.status.set((_("Redid {label}") if redo else _("Undid {label}")).format(label=change.label))
        self._update_undo_menu()

    def _select_only(self, iid: str) -> None:
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self.on_select()

    # ---- grid view (shares the Treeview's rows and selection) ----

    def _tile_px(self) -> int:
        """Tile edge in pixels. Grows with display scaling, at half rate because the window itself does not scale."""
        base = grid_model.TILE_SIZES.get(self.grid_size.get(), grid_model.TILE_SIZES["medium"])
        return int(round(base * (1 + 0.5 * (self._scaled(100) / 100 - 1))))

    def _build_grid(self) -> None:
        self._grid_loader = ThumbnailLoader(workers=2)
        try:
            scale = max(1.0, float(self.tk.call("tk", "scaling")) * 72.0 / 96.0)
        except (tk.TclError, ValueError):
            scale = 1.0
        self.grid_view = ThumbnailGrid(
            self.left_pane,
            rows=lambda: self.records,
            describe=self._tile_info,
            selected=lambda: frozenset(self.tree.selection()),
            focused=self.tree.focus,
            on_click=self._on_tile_click,
            on_activate=self._on_tile_activate,
            tile_px=self._tile_px(),
            scale=scale,
            loader=self._grid_loader,
        )
        self.grid_view.canvas.bind("<Return>", lambda event: self._on_photo_shortcut(event, self.open_fullscreen_viewer))
        self.grid_view.canvas.bind("<KP_Enter>", lambda event: self._on_photo_shortcut(event, self.open_fullscreen_viewer))

    def _tile_info(self, record: ImageRecord) -> TileInfo:
        shot = self._shot_of(record)
        combined = self.combine_pairs.get()
        return TileInfo(
            iid=str(record.id),
            title=shot.stem if combined else record.display_name,
            kind=shot.type_label if combined else record.type_label,
            pick=shot.pick_status,
            glyph=shot.pick_glyph,
            rating=shot.rating,
            thumb=record.thumbnail_path or record.display_source,
            fallback=self._thumbnail_fallback(record),
        )

    def _thumbnail_fallback(self, record: ImageRecord):
        """Worker-thread callback that rebuilds a thumbnail whose file went missing."""
        cache_dir = Path(self.catalog.db_path).parent if self.catalog is not None else None

        def resolve():
            if cache_dir is None:
                return None
            if self._cache_manager is None:
                self._cache_manager = CacheManager(cache_dir)
            return self._cache_manager.thumbnail_for(record)

        return resolve

    def _grid_active(self) -> bool:
        return self.grid_view is not None and self.view_mode.get() == "grid"

    def _row_index(self, iid: str) -> int | None:
        return next((index for index, row in enumerate(self.records) if str(row.id) == iid), None)

    def _list_top_index(self) -> int:
        count = len(self.tree.get_children())
        return int(round(self.tree.yview()[0] * count)) if count else 0

    def _list_scroll_to(self, index: int) -> None:
        count = len(self.tree.get_children())
        if count:
            self.tree.yview_moveto(max(0, index) / count)

    def apply_view_mode(self, persist: bool = True) -> None:
        """Show the list or the thumbnail grid; rows, selection and scroll position carry over."""
        if self.grid_view is None:
            return
        grid_shown = bool(self.grid_view.winfo_manager())
        if self.view_mode.get() == "grid":
            if not grid_shown:
                top = self._list_top_index()
                self.tree.pack_forget()
                self.tree_scrollbar.pack_forget()
                self.grid_view.pack(fill=tk.BOTH, expand=True)
                self.update_idletasks()
                self.grid_view.scroll_to_index(top)
            self.grid_view.canvas.focus_set()
        else:
            if grid_shown:
                top = self.grid_view.top_index()
                self.grid_view.pack_forget()
                self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=(0, 1), pady=0)
                self.tree_scrollbar.pack(fill=tk.Y, side=tk.LEFT)
                self.update_idletasks()
                self._list_scroll_to(top)
            self.tree.focus_set()
        if persist:
            try:
                update_section(SETTINGS_SECTION, {"view_mode": self.view_mode.get()})
            except OSError:
                pass
        self._update_empty_state()

    def toggle_view_mode(self) -> None:
        self.view_mode.set("list" if self.view_mode.get() == "grid" else "grid")
        self.apply_view_mode()

    def apply_grid_size(self) -> None:
        if self.grid_view is not None:
            self.grid_view.set_tile_size(self._tile_px())
        try:
            update_section(SETTINGS_SECTION, {"grid_size": self.grid_size.get()})
        except OSError:
            pass

    def _grid_sync(self, reveal: bool = False) -> None:
        if not self._grid_active():
            return
        if reveal:
            index = self._row_index(self.tree.focus())
            if index is not None:
                self.grid_view.reveal(index)
        self.grid_view.invalidate()

    def _on_tile_click(self, index: int, shift: bool, ctrl: bool) -> None:
        if not 0 <= index < len(self.records):
            return
        iid = str(self.records[index].id)
        if shift:
            self._extend_selection_to(iid)
        elif ctrl:
            self.tree.selection_toggle(iid)
            self.tree.focus(iid)
            self._grid_anchor = iid
            self.on_select()
        else:
            self._grid_anchor = iid
            self._select_only(iid)

    def _extend_selection_to(self, iid: str) -> None:
        order = [str(row.id) for row in self.records]
        anchor = self._grid_anchor if self._grid_anchor in order else (self.tree.focus() or iid)
        self._grid_anchor = anchor
        self.tree.selection_set(grid_model.range_between(order, anchor, iid))
        self.tree.focus(iid)
        self.on_select()

    def _on_tile_activate(self, index: int) -> None:
        if 0 <= index < len(self.records):
            self._select_only(str(self.records[index].id))
            self.open_fullscreen_viewer()

    def move_selection(self, offset: int, vertical: bool = False, extend: bool = False) -> None:
        if self._grid_active():
            self._move_in_grid(offset, vertical, extend)
            return
        children = list(self.tree.get_children())
        if not children:
            return
        selected = self.tree.selection()
        index = children.index(selected[0]) if selected else 0
        next_index = max(0, min(len(children) - 1, index + offset))
        self._select_only(children[next_index])

    def _move_in_grid(self, offset: int, vertical: bool, extend: bool) -> None:
        rows = self.records
        if not rows:
            return
        current = self._row_index(self.tree.focus())
        if current is None:
            selected = self.tree.selection()
            current = self._row_index(selected[0]) if selected else 0
        target = grid_model.move_index(current or 0, grid_model.arrow_key(offset, vertical),
                                       self.grid_view.columns, len(rows))
        iid = str(rows[target].id)
        if extend:
            self._extend_selection_to(iid)
        else:
            self._grid_anchor = iid
            self._select_only(iid)

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
        self._grid_sync()
        # The selection text changes width; re-check whether the shortcut hint still fits beside it.
        self.after_idle(self._layout_footer_hint)

    def show_shortcuts(self) -> None:
        messagebox.showinfo(
            _("Shortcuts"),
            _("P  Pick\n"
              "X  Reject\n"
              "M  Maybe\n"
              "U  Clear pick (Unrated)\n"
              "0\u20135  Star rating (0 clears)\n"
              "\u2190 / \u2192 or \u2191 / \u2193  Move one photo (grid: \u2191 / \u2193 move one row)\n"
              "Shift+arrows, Shift/Ctrl+click  Select several photos\n"
              "G  Switch between grid and list\n"
              "F or Enter  Full screen (Esc to close)\n"
              "Ctrl+Z / Ctrl+Y  Undo / redo marks\n"
              "Ctrl+A  Select all shown\n"
              "Ctrl+O  Choose folder\n"
              "Ctrl+E  Export selected\n"
              "F5  Rescan\n\n"
              "Pick, reject and rating apply to all selected photos. With one photo "
              "selected they advance to the next photo (View > Advance after "
              "Pick/Reject/Rating)."),
        )

    def backup_picked(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("Scan a folder first."))
            return
        shots = self.catalog.list_shots(pick_filter="Pick")
        if not shots:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("No picked images found. Set Pick first."))
            return
        destination = filedialog.askdirectory(title=_("Choose NDEX backup destination"))
        if not destination:
            return
        if not messagebox.askyesno(_("Backup Picked"), backup_confirm_text(shots, destination)):
            return
        # Every file of a picked shot (RAW and JPG) goes into the backup.
        self._start_operation("backup", shot_files(shots), Path(destination))

    def export_xmp_sidecars(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("Scan a folder first."))
            return
        records = self.catalog.list_images()
        if not records:
            messagebox.showinfo(
                NDEX_IMAGE_MANAGER_TITLE,
                _("No images found. Scan a shooting folder first."),
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
        self.status.set(_("Starting {kind} for {images}\u2026").format(
            kind=kind_name(kind).lower(), images=image_count(len(snapshots))))

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
                    warnings.append(_("Could not update catalog backup status: {error}").format(error=exc))
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
                    warnings.append(_("Could not save Job Results. Check the NDEX application data folder."))
            except Exception as exc:
                warnings.append(_("Could not save Job Results: {error}").format(error=exc))
            return summary, warnings

        self._start_worker(kind, work)

    def _operation_finished(self, kind: str, summary, warnings: list[str]) -> None:
        if kind == "backup":
            self.refresh_records()
        destination = getattr(self, "_job_destination", None)
        message = operation_summary_text(kind, summary, destination)
        title = (_("{kind} cancelled") if summary.cancelled else _("{kind} complete")).format(kind=kind_name(kind))
        self.status.set(message)
        details = [message]
        if summary.cancelled:
            details.append(_("The active file finished safely. Unprocessed files are listed in Job Results."))
        elif kind == "xmp" and summary.written == 0 and summary.errors == 0:
            details.append(_("No picked or rated images found. Set pick status or rating first."))
        details.extend(summary.messages[:10])
        details.extend(warnings)
        problem = bool(summary.errors or warnings)
        produced = getattr(summary, "copied", getattr(summary, "exported", getattr(summary, "written", 0)))
        if not summary.cancelled and produced and destination is not None and Path(destination).is_dir():
            details.append(_("Open the destination folder?"))
            if messagebox.askyesno(title, "\n\n".join(details), icon="warning" if problem else "info"):
                _open_folder(destination)
            return
        show = messagebox.showwarning if problem else messagebox.showinfo
        show(title, "\n\n".join(details))

    def send_to_auto_selector(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("Scan a folder first."))
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
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("No picked JPG files to send to Auto Selector.") + note)
            return
        question = send_confirm_text(len(files), "JPG", "Auto Selector")
        if without_jpg:
            question += f"\n\n{no_jpg_text(without_jpg)}"
        if not messagebox.askyesno(_("Send Picks to Auto Selector"), question):
            return
        handoff = record_select_handoff(
            self.source_dir or files[0].parent, files, target="auto_selector"
        )
        if handoff is None:
            messagebox.showerror(
                NDEX_IMAGE_MANAGER_TITLE,
                _("Could not write the handoff file, so the picks were not sent. "
                  "Check that %LOCALAPPDATA%\\NDEX is writable."),
            )
            return
        args: list[str] = ["--open", "--handoff", str(handoff)]
        if self.source_dir is not None:
            args.extend(["--raw-source", str(self.source_dir)])
        launched = launch_app("auto_selector", args)
        if not launched:
            messagebox.showerror(
                NDEX_IMAGE_MANAGER_TITLE,
                _("Could not find NDEX Auto Selector. Build or install it first."),
            )
        elif without_jpg:
            self.status.set(_("Sent {files}. {note}").format(
                files=picked_jpg_count(len(files)), note=no_jpg_text(without_jpg, sent=True)))

    def send_picks_to_frame(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("Scan a folder first."))
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
                _("No picked JPG/PNG/TIFF files to send. Frame does not import RAW."),
            )
            return
        noun = "JPG" if all(Path(path).suffix.casefold() in (".jpg", ".jpeg") for path in files) else "file"
        if not messagebox.askyesno(_("Send Picks to Frame"), send_confirm_text(len(files), noun, "Frame")):
            return
        handoff = record_select_handoff(self.source_dir or files[0].parent, files)
        if handoff is None:
            messagebox.showerror(
                NDEX_IMAGE_MANAGER_TITLE,
                _("Could not write the handoff file, so the picks were not sent. "
                  "Check that %LOCALAPPDATA%\\NDEX is writable."),
            )
            return
        launched = launch_app("frame", ["--open", "--handoff", str(handoff)])
        if not launched:
            messagebox.showerror(
                NDEX_IMAGE_MANAGER_TITLE,
                _("Could not find NDEX Frame. Build or install it first."),
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
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("Select one or more images first."))
            return
        if self.combine_pairs.get():
            # A combined row stands for its whole shot: export every file of it.
            shots = self._shots_of(rows)
            records = shot_files(shots)
            heading = _("Export {shots} ({files})").format(
                shots=selected_shot_count(len(shots)), files=file_counts_text(records))
        else:
            records = rows
            heading = ngettext("Export {count} selected image", "Export {count} selected images",
                               len(records)).format(count=len(records))

        dialog = tk.Toplevel(self)
        dialog.title(_("Export Selected Images"))
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

        ttk.Label(body, text=_("Destination"), style="CardMuted.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=destination, width=54).grid(row=1, column=1, sticky=tk.EW, padx=(8, 6))
        ttk.Button(
            body,
            text=_("Browse"),
            command=lambda: self._choose_export_destination(destination),
        ).grid(row=1, column=2, sticky=tk.EW)

        ttk.Label(body, text=_("Rename pattern"), style="CardMuted.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=pattern, width=54).grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=(8, 0))

        ttk.Label(body, text=_("Start index"), style="CardMuted.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        ttk.Spinbox(body, from_=1, to=99999, textvariable=start_index, width=10).grid(row=3, column=1, sticky=tk.W, padx=(8, 0))

        ttk.Label(body, text=_("Duplicate"), style="CardMuted.TLabel").grid(row=4, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(
            body,
            textvariable=duplicate_policy,
            values=("rename", "skip", "overwrite"),
            width=12,
            state="readonly",
        ).grid(row=4, column=1, sticky=tk.W, padx=(8, 0))

        # The braces are literal rename-pattern tokens, so this text is never passed to str.format.
        help_text = _(
            "Tokens: {date}, {time}, {index}, {index4}, {name}, {rating}, {pick}, {ext}\n"
            "Example: NDEX_{date}_{index}_{name}"
        )
        ttk.Label(body, text=help_text, style="CardMuted.TLabel").grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=(10, 4))

        button_row = ttk.Frame(body, style="CardInner.TFrame")
        button_row.grid(row=6, column=0, columnspan=3, sticky=tk.E, pady=(12, 0))
        ttk.Button(button_row, text=_("Cancel"), command=dialog.destroy).pack(side=tk.RIGHT)
        ttk.Button(
            button_row,
            text=_("Export"),
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
        selected = filedialog.askdirectory(title=_("Choose export destination"))
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
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("Choose an export destination."))
            return
        try:
            safe_start_index = max(1, int(start_index))
        except (TypeError, ValueError):
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, _("Start index must be a number."))
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

        tk.Button(controls, text=_("Previous"), command=lambda: navigate(-1), width=10).pack(side=tk.LEFT)
        tk.Button(controls, text=_("Next"), command=lambda: navigate(1), width=10).pack(side=tk.LEFT, padx=(6, 14))
        tk.Label(
            controls,
            text=_("Rating"),
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

        tk.Button(controls, text=_("Clear"), command=lambda: set_fullscreen_rating(0, False), width=8).pack(side=tk.LEFT, padx=(8, 18))
        tk.Label(
            controls,
            text=_("\u2190/\u2192 move   0\u20135 rating   P/M/X/U pick   Esc/F/double-click close"),
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
            badge_text, badge_color = pick_badge(current_shot.pick_status)
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
            self.preview_label.configure(image="", text=_("No preview"))
            self.preview_image = None
            self.summary_text.set(_("Select an image to see EXIF summary."))
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
            self.summary_text.set(_("Select an image to see EXIF summary."))
        self.detail_text.configure(state=tk.DISABLED)

    def _row_title(self, record: ImageRecord) -> str:
        if self.combine_pairs.get():
            shot = self._shot_of(record)
            return f"{shot.stem} ({shot.type_label})" if len(shot.records) > 1 else record.display_name
        return record.display_name

    def _file_lines(self, record: ImageRecord) -> list[str]:
        shot = self._shot_of(record)
        if self.combine_pairs.get() and len(shot.records) > 1:
            return [_("Files: {names}").format(names=" + ".join(shot.file_names))]
        return [_("File: {name}").format(name=record.display_name)]

    def _simple_detail_lines(self, record: ImageRecord) -> list[str]:
        shot = self._shot_of(record)
        return [
            *self._file_lines(record),
            _("Capture: {when}").format(when=f"{record.effective_datetime:%Y-%m-%d %H:%M:%S}"),
            _("Camera: {value}").format(value=record.camera_model or "-"),
            _("Lens: {value}").format(value=record.lens_model or "-"),
            self._exposure_line(record),
            _("Selection: {pick} / Rating: {rating}").format(pick=pick_label(shot.pick_status),
                                                           rating=_rating_text(shot.rating)),
        ]

    def _full_detail_lines(self, record: ImageRecord) -> list[str]:
        shot = self._shot_of(record)
        combined = self.combine_pairs.get() and len(shot.records) > 1
        paths = ([_("Path: {path}").format(path=member.file_path) for member in shot.records] if combined
                 else [_("Path: {path}").format(path=record.file_path)])
        sizes = (
            [_("Files: {names}").format(names=", ".join(f"{m.type_label} {m.file_size or '-'}" for m in shot.records))]
            if combined else []
        )

        def value(text: str) -> str:
            return text or "-"

        return [
                *paths,
                *sizes,
                _("Capture: {when}").format(when=f"{record.effective_datetime:%Y-%m-%d %H:%M:%S}"),
                _("Modified: {when}").format(when=f"{record.file_modified_datetime:%Y-%m-%d %H:%M:%S}"),
                _("Camera: {value}").format(value=value(record.camera_model)),
                _("Lens: {value}").format(value=value(record.lens_model)),
                _("Focal length: {value}").format(value=value(record.focal_length)),
                self._exposure_line(record),
                _("Exposure compensation: {value}").format(value=value(record.exposure_compensation)),
                _("White balance: {value}").format(value=value(record.white_balance)),
                _("Size: {width} x {height} / {file_size}").format(
                    width=record.width or "-", height=record.height or "-", file_size=value(record.file_size)),
                _("Color: {color} / GPS: {gps}").format(color=value(record.color_space), gps=value(record.gps)),
                _("Pair: {pair} / Proxy: {proxy}").format(pair=record.pair_status, proxy=record.proxy_status),
                _("Backup: {value}").format(value=record.backup_status),
                _("Selection: {pick} / Rating: {rating}").format(pick=pick_label(shot.pick_status),
                                                               rating=_rating_text(shot.rating)),
                _("Note: {value}").format(value=value(record.note)),
        ]

    @staticmethod
    def _exposure_line(record: ImageRecord) -> str:
        return _("Exposure: {shutter} / f/{aperture} / ISO {iso}").format(
            shutter=record.exposure_time or "-", aperture=record.aperture or "-", iso=record.iso or "-")

    def _fullscreen_detail_text(self, record: ImageRecord) -> str:
        shot = self._shot_of(record)
        return (
            f"{self._row_title(record)}   {_rating_text(shot.rating)}   {pick_label(shot.pick_status)}\n"
            f"{self._summary_line(record)}"
        )

    def _summary_line(self, record: ImageRecord) -> str:
        return _("{camera} | {lens} | f/{aperture} | {shutter} | ISO {iso} | {resolution}").format(
            camera=record.camera_model or "-", lens=record.lens_model or "-",
            aperture=record.aperture or "-", shutter=record.exposure_time or "-",
            iso=record.iso or "-", resolution=_resolution_text(record))

    def _refresh_rating_widgets(self, rating: int) -> None:
        _refresh_star_labels(self.star_labels, rating)


def _rating_text(rating: int) -> str:
    return _("none") if rating <= 0 else STAR_FILLED * rating


def _resolution_text(record: ImageRecord) -> str:
    if record.width and record.height:
        return f"{record.width} x {record.height}"
    return _("resolution -")


def _refresh_star_labels(labels: list[tk.Label], rating: int) -> None:
    for index, star in enumerate(labels, start=1):
        star.configure(text=STAR_FILLED if index <= rating else STAR_EMPTY, fg=STAR if index <= rating else "#6b7280")


def run_app(initial_source: Path | None = None) -> None:
    app = ImageManagerApp(initial_source=initial_source)
    app.mainloop()
