from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .backup_executor import execute_backup
from .app_paths import get_user_data_dir
from .branding import NDEX_ONE_TITLE
from .config import ConfigManager
from .file_types import FILE_TYPE_ORDER, RAW_BRANDS, get_file_type_group, get_file_type_label, get_visible_file_types
from .folder_manager import build_preview
from .logger import AppLogger, format_display_line
from .metadata import MetadataExtractor
from .scanner import analyze_source, build_scan_items, same_folder

from ndex_common import i18n
from ndex_common.i18n import _, ngettext
from ndex_common.launch import launch_app
from ndex_common.theme import CARD_BG, ScrollableFrame, apply_tk_theme, apply_window_icon, build_app_header, style_text_widget

# Display text is looked up when needed, not at import, so the language chosen
# in main() applies. The internal keys ("size", "rename", "smart", ...) are what
# the saved config holds; labels are only ever derived from them for display.


def verify_mode_labels() -> dict[str, str]:
    return {
        "size": _("Quick check (file size)"),
        "sha256": _("Full check (every byte)"),
        "none": _("No check"),
    }


def verify_mode_hints() -> dict[str, str]:
    return {
        "size": _("Compares file sizes. Fast."),
        "sha256": _("Compares every byte. Slower, safest for memory cards."),
        "none": _("Fastest, but a bad copy would go unnoticed."),
    }


def duplicate_policy_labels() -> dict[str, str]:
    return {
        "rename": _("Keep both (rename new copy)"),
        "smart": _("Skip identical files"),
        "skip": _("Skip same-name files"),
        "overwrite": _("Overwrite existing"),
    }


def duplicate_policy_hints() -> dict[str, str]:
    return {
        "rename": _("If a file with the same name exists, the new copy is saved as IMG_0001_001.JPG."),
        "smart": _(
            "Skips files whose content is exactly the same; a different photo with the "
            "same name is saved as a renamed copy."
        ),
        "skip": _("Leaves existing files alone, even if the photo differs."),
        "overwrite": _("Replaces existing files. The old version cannot be recovered."),
    }


def empty_state_text() -> str:
    return _(
        "1. Choose the card or folder to copy from.\n"
        "2. Choose where backups are kept.\n"
        "3. Press Analyze."
    )


def rule_hint_before() -> str:
    return _("Photos go into Year\\Month\\MonthDay\\type folders by the date taken.")


def invalid_source_message() -> str:
    return _("This folder doesn't exist. Reinsert the card or choose it again with Browse.")


def cancel_hint() -> str:
    return _("Cancel is available while copying.")


def analyzing_suffix() -> str:
    return _("reading dates only; nothing is copied yet")


def stopping_status() -> str:
    return _("Stopping after the current file… files already copied are kept.")


def preview_status_label(status: str) -> str:
    """Folder-preview status for display; ``status`` stays the internal English key."""
    return {"Existing": _("Existing"), "Mixed": _("Mixed"), "New": _("New")}.get(status, status)


def format_size(num_bytes: int) -> str:
    """Human size such as "1.8 GB" (1024-based, one decimal above bytes)."""
    size = float(max(num_bytes, 0))
    if size < 1024:
        return f"{int(size)} B"
    for unit in ("KB", "MB", "GB"):
        size /= 1024
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} GB"  # pragma: no cover - the loop always returns


def _files(count: int) -> str:
    return ngettext("{count} file", "{count} files", count).format(count=count)


def grouped_counts(counts: dict[str, int]) -> dict[str, int]:
    """Counts per file type folded into JPG and RAW, empty groups left out."""
    grouped: dict[str, int] = {}
    for file_type in FILE_TYPE_ORDER:
        count = counts.get(file_type, 0)
        if count:
            group = get_file_type_group(file_type)
            grouped[group] = grouped.get(group, 0) + count
    return grouped


def format_type_counts(counts: dict[str, int], pattern: str = "{group} {count}", separator: str = " · ") -> str:
    """"JPG 24 · RAW 18", or "None" when there are no files."""
    return separator.join(
        pattern.format(group=group, count=count) for group, count in grouped_counts(counts).items()
    ) or _("None")


def format_day_span(date_range) -> str:
    """"3 days (2026-09-05 to 2026-09-07)", or "" when there are no dates."""
    first, last = date_range
    if not first or not last:
        return ""
    first_day, last_day = first.date(), last.date()
    if first_day == last_day:
        one_day = ngettext("{count} day", "{count} days", 1).format(count=1)
        return f"{one_day} ({first_day:%Y-%m-%d})"
    days = (last_day - first_day).days + 1
    return _("{days} ({first} to {last})").format(
        days=ngettext("{count} day", "{count} days", days).format(count=days),
        first=f"{first_day:%Y-%m-%d}",
        last=f"{last_day:%Y-%m-%d}",
    )


def free_space_warning(total_size: int, free_space: int | None) -> str:
    """A warning when the destination disk is too small, else an empty string."""
    if free_space is None or free_space >= total_size:
        return ""
    return _("Not enough free space: {needed} needed, only {free} free on the destination.").format(
        needed=format_size(total_size), free=format_size(free_space)
    )


def fallback_note(count: int) -> str:
    if count <= 0:
        return ""
    return ngettext(
        "{count} file had no capture date; its modified date was used.",
        "{count} files had no capture date; their modified date was used.",
        count,
    ).format(count=count)


def example_folder_text(summary) -> str:
    """A live example of where the first file will go."""
    if not summary.items:
        return rule_hint_before()
    first = min(summary.items, key=lambda item: (item.capture_datetime, str(item.source_path).lower()))
    return _("Folders will look like: {path}").format(path=first.destination_dir)


def build_confirmation(summary, policy_label: str, verify_label: str, dry_run: bool) -> tuple[str, str]:
    """Title and body of the dialog shown before copying, built from the analysis."""
    lines = [
        _("Copy {files} ({size}) to {destination}?").format(
            files=_files(len(summary.items)),
            size=format_size(summary.total_size),
            destination=summary.backup_root,
        )
    ]
    detail = format_type_counts(summary.counts, separator=", ") if summary.items else ""
    span = format_day_span(summary.date_range)
    if detail or span:
        lines.append(" · ".join(part for part in (detail, span) if part))
    lines.append(_("If a file already exists: {policy}").format(policy=policy_label))
    lines.append(_("After copying: {check}").format(check=verify_label))
    lines.append(_("Nothing is deleted from the source."))
    if dry_run:
        lines.append(_("Nothing will be copied."))
    else:
        warning = free_space_warning(summary.total_size, summary.free_space)
        if warning:
            lines.extend(["", warning])
    return (_("Start Dry Run") if dry_run else _("Start Backup")), "\n".join(lines)


def not_run_count(result) -> int:
    """Files a stopped backup never reached (they stay retryable in Job Results)."""
    return sum(1 for entry in result.items if entry.get("detail") == "not run: cancelled")


def build_completion_status(result) -> str:
    """The one-line outcome shown in the status bar after a backup finishes."""
    if result.cancelled:
        return _("Stopped: {copied} copied; {not_run} not run (see Job Results to retry).").format(
            copied=result.copied, not_run=not_run_count(result)
        )
    if result.dry_run:
        return _("Dry run done: {files} would be copied, {skipped} skipped. Nothing was copied.").format(
            files=_files(result.copied), skipped=result.skipped
        )
    if result.total and result.skipped == result.total and not result.errors:
        return _("Nothing new to copy: all {total} files were already in the backup.").format(
            total=result.total
        )
    if result.copied and result.verified == result.copied:
        copied = _("{copied} copied and verified").format(copied=result.copied)
    elif result.copied and not result.verified:
        copied = _("{copied} copied (not verified)").format(copied=result.copied)
    elif result.copied:
        copied = _("{copied} copied, {verified} verified").format(
            copied=result.copied, verified=result.verified
        )
    else:
        copied = _("0 copied")
    return _("Done: {copied}, {skipped} skipped, {errors} errors.").format(
        copied=copied, skipped=result.skipped, errors=result.errors
    )


class Tooltip:
    """A small hover hint for a widget."""

    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip is not None:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tip, text=self.text, background="#FFFBE6", foreground="#222222",
            relief="solid", borderwidth=1, padx=6, pady=3,
        ).pack()
        self._tip = tip

    def _hide(self, _event=None) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class DSBApp(tk.Tk):
    def __init__(
        self,
        initial_source: Path | None = None,
        initial_destination: Path | None = None,
        preload_only: bool = False,
        retry_manifest: Path | None = None,
    ):
        super().__init__()
        i18n.init("ndex_one") if i18n.current_language() == i18n.DEFAULT_LANGUAGE and not i18n.available_languages() else None
        self.title(NDEX_ONE_TITLE)
        initial_height = min(820, max(600, self.winfo_screenheight() - 120))
        self.geometry(f"1220x{initial_height}")
        self.minsize(1080, 600)
        self.brand_images: list[tk.PhotoImage] = []
        apply_window_icon(self, self.brand_images)
        apply_tk_theme(self)

        self.root_dir = get_user_data_dir()
        self.config_manager = ConfigManager()
        self.settings = self.config_manager.load()
        self.ui_queue: queue.Queue = queue.Queue()
        self.logger = AppLogger(sink=self._queue_log, display=self._display_log_line)
        self.metadata_extractor = MetadataExtractor.from_settings(self.settings)

        self.current_summary = None
        self.worker_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.is_busy = False
        self.is_analyzing = False
        self._closing = False
        self._input_controls: list[ttk.Widget] = []
        self.pending_analysis: dict | None = None
        self.pending_backup: dict | None = None
        self._last_progress_at = 0.0

        # With preload_only the caller passed the folders to use (NDEX handoff),
        # so remembered folders stay out of the way and "Open Empty" is empty.
        remembered_source = "" if preload_only else self.settings.get("last_source", "")
        remembered_destination = "" if preload_only else self.settings.get("last_destination", "")
        self.source_var = tk.StringVar(value=str(initial_source) if initial_source else remembered_source)
        self.destination_var = tk.StringVar(
            value=str(initial_destination) if initial_destination else remembered_destination
        )
        duplicate_labels = duplicate_policy_labels()
        verify_labels = verify_mode_labels()
        self.duplicate_var = tk.StringVar(
            value=duplicate_labels.get(
                self.settings.get("duplicate_policy", "rename"), duplicate_labels["rename"]
            )
        )
        self.verify_var = tk.StringVar(
            value=verify_labels.get(
                self.settings.get("verify_mode", "size"), verify_labels["size"]
            )
        )
        self.dry_run_var = tk.BooleanVar(value=self.settings.get("dry_run", False))
        self.brand_vars = {
            brand_key: tk.BooleanVar(value=self.settings["raw_brands"].get(brand_key, False))
            for brand_key in RAW_BRANDS
        }
        self.type_vars = {
            file_type: tk.BooleanVar(value=self.settings["default_file_types"].get(file_type, True))
            for file_type in FILE_TYPE_ORDER
        }
        self.type_checkbuttons: dict[str, ttk.Checkbutton] = {}
        self.status_var = tk.StringVar(value=_("Ready."))
        self.summary_var = tk.StringVar(value=empty_state_text())
        self._summary_text = empty_state_text()
        self.rule_var = tk.StringVar(value=rule_hint_before())
        self.duplicate_hint_var = tk.StringVar()
        self.verify_hint_var = tk.StringVar()
        self._wrap_labels: list[tuple[ttk.Label, tk.Misc, int]] = []
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_layout()
        self._bind_events()
        self.protocol("WM_DELETE_WINDOW", self._request_close)
        self._update_button_states()
        self.after(100, self._process_ui_queue)
        if retry_manifest is not None:
            # From the Launcher's "Retry in NDEX One...". Open at that job;
            # the user presses Retry here, where the settings are visible.
            self.after(150, lambda: self._open_job_results(select=Path(retry_manifest)))

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = build_app_header(
            self,
            title=NDEX_ONE_TITLE,
            tagline=_("Analyze camera files, preview the folder tree, then run a safe backup."),
            holder=self.brand_images,
        )
        header.grid(row=0, column=0, sticky="ew")

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        left_panel = ttk.Frame(body, padding=12, style="Card.TFrame")
        right = ttk.Frame(body, padding=16, style="Card.TFrame")
        body.add(left_panel, weight=3)
        body.add(right, weight=4)
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(0, weight=1)
        self.options_viewport = ScrollableFrame(
            left_panel, style="CardInner.TFrame", content_style="CardInner.TFrame", background=CARD_BG,
        )
        self.options_viewport.grid(row=0, column=0, sticky="nsew")
        left = self.options_viewport.content
        # A useful initial sash position must not depend on the canvas's tiny request size.
        self.after_idle(lambda: body.sashpos(0, max(500, int(body.winfo_width() * 0.48))))

        for frame in (left, right):
            frame.columnconfigure(1, weight=1)

        ttk.Label(left, text=_("Source Folder"), style="CardSection.TLabel").grid(row=0, column=0, sticky="w")
        source_entry = ttk.Entry(left, textvariable=self.source_var)
        source_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        source_browse = ttk.Button(left, text=_("Browse"), command=self._browse_source)
        source_browse.grid(row=1, column=2, padx=(8, 0))
        self._input_controls.extend((source_entry, source_browse))

        ttk.Label(left, text=_("Backup Destination"), style="CardSection.TLabel").grid(row=2, column=0, sticky="w")
        destination_entry = ttk.Entry(left, textvariable=self.destination_var)
        destination_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        destination_browse = ttk.Button(left, text=_("Browse"), command=self._browse_destination)
        destination_browse.grid(row=3, column=2, padx=(8, 0))
        self._input_controls.extend((destination_entry, destination_browse))

        ttk.Label(left, text=_("File Types"), style="CardSection.TLabel").grid(row=4, column=0, sticky="w")
        types_frame = ttk.Frame(left, style="CardInner.TFrame")
        types_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(2, 6))
        types_frame.columnconfigure(0, weight=1)
        self.brand_frame = ttk.Frame(types_frame, style="CardInner.TFrame")
        self.brand_frame.grid(row=0, column=0, sticky="w")
        for column, (brand_key, brand) in enumerate(RAW_BRANDS.items()):
            brand_button = ttk.Checkbutton(
                self.brand_frame,
                text=brand["label"],
                variable=self.brand_vars[brand_key],
                command=self._refresh_file_type_options,
                style="Card.TCheckbutton",
            )
            brand_button.grid(row=0, column=column, sticky="w", padx=(0, 12))
            self._input_controls.append(brand_button)

        self.types_frame = ttk.Frame(types_frame, style="CardInner.TFrame")
        self.types_frame.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.types_frame.bind("<Configure>", self._layout_file_type_options, add="+")
        for index, file_type in enumerate(FILE_TYPE_ORDER):
            checkbutton = ttk.Checkbutton(
                self.types_frame,
                text=get_file_type_label(file_type),
                variable=self.type_vars[file_type],
                style="Card.TCheckbutton",
            )
            row = index // 3
            column = index % 3
            checkbutton.grid(row=row, column=column, sticky="w", padx=(0, 12))
            self.type_checkbuttons[file_type] = checkbutton
            self._input_controls.append(checkbutton)
        self._refresh_file_type_options()

        # Each option is one row (label, combobox) with its hint underneath.
        options = ttk.Frame(left, style="CardInner.TFrame")
        options.grid(row=6, column=0, columnspan=3, sticky="ew")
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text=_("Duplicates"), style="CardSection.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        duplicate_combo = ttk.Combobox(
            options,
            textvariable=self.duplicate_var,
            values=list(duplicate_policy_labels().values()),
            state="readonly",
        )
        duplicate_combo.grid(row=0, column=1, sticky="ew")
        duplicate_hint = ttk.Label(options, textvariable=self.duplicate_hint_var, style="CardMuted.TLabel", justify="left")
        duplicate_hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 6))

        ttk.Label(options, text=_("Verify copy"), style="CardSection.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10))
        verify_combo = ttk.Combobox(
            options,
            textvariable=self.verify_var,
            values=list(verify_mode_labels().values()),
            state="readonly",
        )
        verify_combo.grid(row=2, column=1, sticky="ew")
        verify_hint = ttk.Label(options, textvariable=self.verify_hint_var, style="CardMuted.TLabel", justify="left")
        verify_hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 4))
        self._input_controls.extend((duplicate_combo, verify_combo))
        self._wrap_labels.extend(((duplicate_hint, left, 40), (verify_hint, left, 40)))
        duplicate_combo.bind("<<ComboboxSelected>>", self._update_option_hints)
        verify_combo.bind("<<ComboboxSelected>>", self._update_option_hints)
        self.duplicate_var.trace_add("write", self._update_option_hints)
        self.verify_var.trace_add("write", self._update_option_hints)
        self._update_option_hints()

        dry_run_button = ttk.Checkbutton(
            left,
            text=_("Dry Run (preview only, do not copy files)"),
            variable=self.dry_run_var,
            style="Card.TCheckbutton",
        )
        dry_run_button.grid(row=7, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self._input_controls.append(dry_run_button)

        rule_label = ttk.Label(left, textvariable=self.rule_var, style="CardMuted.TLabel", justify="left")
        rule_label.grid(row=8, column=0, columnspan=3, sticky="w")
        self._wrap_labels.append((rule_label, left, 40))

        buttons = ttk.Frame(left_panel, style="CardInner.TFrame")
        buttons.grid(row=1, column=0, sticky="ew", pady=(8, 6))
        for column in range(2):
            buttons.columnconfigure(column, weight=1, uniform="actions")
        self.analyze_button = ttk.Button(buttons, text=_("Analyze"), command=self._start_analysis)
        self.backup_button = ttk.Button(buttons, text=_("Start Backup"), command=self._start_backup)
        self.cancel_button = ttk.Button(buttons, text=_("Cancel"), command=self._cancel_task)
        self.results_button = ttk.Button(buttons, text=_("Job Results..."), command=self._open_job_results)
        self.open_button = ttk.Button(buttons, text=_("Open Backup Folder"), command=self._open_backup_folder)
        self.handoff_button = ttk.Button(
            buttons, text=_("Open in Image Manager"), command=self._open_in_image_manager
        )
        self.analyze_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.backup_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.cancel_button.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(6, 0))
        self.results_button.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(6, 0))
        self.open_button.grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=(6, 0))
        self.handoff_button.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=(6, 0))
        Tooltip(self.cancel_button, cancel_hint())

        progress_frame = ttk.LabelFrame(left_panel, text=_("Progress"), padding=(10, 6))
        progress_frame.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        progress_frame.columnconfigure(0, weight=1)
        progress_frame.rowconfigure(1, minsize=38)  # room for two status lines
        ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100).grid(row=0, column=0, sticky="ew")
        status_label = ttk.Label(progress_frame, textvariable=self.status_var, style="CardMuted.TLabel", justify="left")
        status_label.grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self._wrap_labels.append((status_label, left_panel, 48))
        left.bind("<Configure>", self._rewrap_labels, add="+")
        left_panel.bind("<Configure>", self._rewrap_labels, add="+")

        right.rowconfigure(3, weight=2, minsize=80)
        right.rowconfigure(5, weight=3, minsize=64)

        ttk.Label(right, text=_("Summary"), style="CardSection.TLabel").grid(row=0, column=0, sticky="w")
        summary_label = ttk.Label(right, textvariable=self.summary_var, justify="left", style="Card.TLabel")
        summary_label.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        self._wrap_labels.append((summary_label, right, 56))
        right.bind("<Configure>", self._rewrap_labels, add="+")
        # Start narrow so long paths cannot widen a pane; the real width is applied on resize.
        for wrapped, _container, _margin in self._wrap_labels:
            wrapped.configure(wraplength=300)

        ttk.Label(right, text=_("Date Preview"), style="CardSection.TLabel").grid(row=2, column=0, sticky="w")
        columns = ("date", "folder", "files", "status")
        headings = {
            "date": _("Date"), "folder": _("Folder"), "files": _("Files"), "status": _("Status"),
        }
        self.preview_treeview = ttk.Treeview(right, columns=columns, show="headings", height=10)
        self.preview_treeview.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        for column, width in zip(columns, (90, 140, 140, 70)):
            self.preview_treeview.heading(column, text=headings[column])
            self.preview_treeview.column(column, width=width, minwidth=50, anchor="w")
        tree_scroll = ttk.Scrollbar(right, orient="vertical", command=self.preview_treeview.yview)
        tree_scroll.grid(row=3, column=1, sticky="ns", pady=(6, 0))
        self.preview_treeview.configure(yscrollcommand=tree_scroll.set)

        ttk.Label(right, text=_("Folder Tree Preview"), style="CardSection.TLabel").grid(
            row=4, column=0, sticky="w", pady=(12, 0)
        )
        self.folder_preview = tk.Text(right, height=10, width=20, wrap="none")
        style_text_widget(self.folder_preview)
        self.folder_preview.grid(row=5, column=0, sticky="nsew", pady=(6, 0))
        folder_scroll = ttk.Scrollbar(right, orient="vertical", command=self.folder_preview.yview)
        folder_scroll.grid(row=5, column=1, sticky="ns", pady=(6, 0))
        self.folder_preview.configure(yscrollcommand=folder_scroll.set)

        ttk.Label(right, text=_("Log"), style="CardSection.TLabel").grid(row=6, column=0, sticky="w", pady=(12, 0))
        self.log_text = tk.Text(right, height=12, width=20, wrap="word")
        style_text_widget(self.log_text)
        self.log_text.grid(row=7, column=0, sticky="nsew", pady=(6, 0))
        log_scroll = ttk.Scrollbar(right, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=7, column=1, sticky="ns", pady=(6, 0))
        self.log_text.configure(yscrollcommand=log_scroll.set)
        right.rowconfigure(7, weight=2, minsize=80)

    def _bind_events(self) -> None:
        for variable in (self.source_var, self.destination_var, *self.type_vars.values(), *self.brand_vars.values()):
            variable.trace_add("write", self._invalidate_analysis)
        self.bind("<Return>", self._on_enter)
        self.bind("<KP_Enter>", self._on_enter)

    def _rewrap_labels(self, _event=None) -> None:
        for label, container, margin in self._wrap_labels:
            width = container.winfo_width() - margin
            if width > 100:
                label.configure(wraplength=width)

    def _update_option_hints(self, *_args) -> None:
        self.duplicate_hint_var.set(duplicate_policy_hints()[self._selected_duplicate_policy()])
        self.verify_hint_var.set(verify_mode_hints()[self._selected_verify_mode()])

    def _primary_action(self):
        """(button, command) the Enter key triggers: Analyze first, Start Backup once analyzed."""
        if self.current_summary is not None:
            return self.backup_button, self._start_backup
        return self.analyze_button, self._start_analysis

    def _on_enter(self, event=None) -> str | None:
        focused = self.focus_get()
        # Enter in the logs or on another button keeps its usual meaning.
        if isinstance(focused, (tk.Text, ttk.Button, ttk.Combobox)):
            return None
        button, command = self._primary_action()
        if str(button.cget("state")) == "disabled":
            return None
        command()
        return "break"

    def _invalidate_analysis(self, *_args) -> None:
        had_plan = self.current_summary is not None
        self.current_summary = None
        if not self.is_busy:
            if had_plan:
                self.summary_var.set(_("Folders or file types changed. Press Analyze to update the plan."))
                self.status_var.set(_("Press Analyze to update the backup plan."))
            else:
                self.summary_var.set(empty_state_text())
            self.rule_var.set(rule_hint_before())
        self._update_button_states()

    def _browse_source(self) -> None:
        selected = filedialog.askdirectory(title=_("Select source folder"))
        if selected:
            self.source_var.set(selected)

    def _browse_destination(self) -> None:
        selected = filedialog.askdirectory(title=_("Select backup destination"))
        if selected:
            self.destination_var.set(selected)

    def _selected_types(self) -> list[str]:
        visible_types = self._visible_file_types()
        return [file_type for file_type in visible_types if self.type_vars[file_type].get()]

    def _enabled_brands(self) -> dict[str, bool]:
        return {brand_key: brand_var.get() for brand_key, brand_var in self.brand_vars.items()}

    def _visible_file_types(self) -> list[str]:
        return get_visible_file_types(self._enabled_brands())

    def _refresh_file_type_options(self) -> None:
        self._layout_file_type_options()
        if hasattr(self, "analyze_button"):
            self._update_button_states()

    def _layout_file_type_options(self, _event=None) -> None:
        visible_types = self._visible_file_types()
        widest = max((self.type_checkbuttons[key].winfo_reqwidth() for key in visible_types), default=1)
        available = self.options_viewport.content.winfo_width()
        columns = max(1, min(3, available // (widest + 12)))
        for file_type in FILE_TYPE_ORDER:
            checkbutton = self.type_checkbuttons[file_type]
            if file_type in visible_types:
                index = visible_types.index(file_type)
                row = index // columns
                column = index % columns
                checkbutton.grid(row=row, column=column, sticky="w", padx=(0, 12), pady=(2, 0))
            else:
                checkbutton.grid_remove()

    def _selected_verify_mode(self) -> str:
        label = self.verify_var.get()
        for mode, text in verify_mode_labels().items():
            if text == label:
                return mode
        return "size"

    def _selected_duplicate_policy(self) -> str:
        label = self.duplicate_var.get()
        for policy, text in duplicate_policy_labels().items():
            if text == label:
                return policy
        return "rename"

    def _save_settings(self) -> None:
        self.config_manager.save(
            {
                "duplicate_policy": self._selected_duplicate_policy(),
                "verify_mode": self._selected_verify_mode(),
                "dry_run": self.dry_run_var.get(),
                "last_source": self.source_var.get(),
                "last_destination": self.destination_var.get(),
                "default_file_types": {
                    file_type: file_type_var.get()
                    for file_type, file_type_var in self.type_vars.items()
                },
                "raw_brands": self._enabled_brands(),
            }
        )
        try:
            from ndex_common.session import remember

            remember(
                "ndex_one",
                folders={
                    "source": self.source_var.get().strip(),
                    "destination": self.destination_var.get().strip(),
                },
            )
        except OSError:
            pass

    def _start_analysis(self) -> None:
        if self.is_busy or self._closing:
            return
        if not self.source_var.get().strip() or not self.destination_var.get().strip():
            messagebox.showerror(_("Missing Folder"), _("Select both source and backup destination folders."))
            return
        source = Path(self.source_var.get().strip())
        destination = Path(self.destination_var.get().strip())
        if not source.is_dir():
            messagebox.showerror(_("Invalid Source"), invalid_source_message())
            return
        if not self._destination_usable(destination):
            return
        if same_folder(source, destination):
            messagebox.showerror(
                _("Invalid Destination"),
                _("The backup destination must be different from the source folder."),
            )
            return
        selected_types = self._selected_types()
        if not selected_types:
            messagebox.showwarning(_("No File Types"), _("Select at least one file type to scan."))
            return

        self._save_settings()
        self.current_summary = None
        self.pending_analysis = {
            "source_dir": source,
            "backup_root": destination,
            "enabled_types": selected_types,
        }
        # The analysis loop has no cancellation point, so Cancel stays disabled.
        self.is_analyzing = True
        self._set_busy(
            True,
            _("Analyzing files — {detail}. {cancel_hint}").format(
                detail=analyzing_suffix(), cancel_hint=cancel_hint()
            ),
        )
        self._run_worker(self._analyze_worker)

    def _destination_usable(self, destination: Path) -> bool:
        """A backup root that exists as a folder, or can be created in one."""
        if destination.exists() and not destination.is_dir():
            messagebox.showerror(_("Invalid Destination"), _("Backup destination must be a folder."))
            return False
        if not destination.exists() and not destination.parent.exists():
            messagebox.showerror(
                _("Invalid Destination"), _("Select a destination whose parent folder already exists.")
            )
            return False
        return True

    def _analyze_worker(self) -> None:
        summary = analyze_source(
            source_dir=self.pending_analysis["source_dir"],
            backup_root=self.pending_analysis["backup_root"],
            metadata_extractor=self.metadata_extractor,
            enabled_types=self.pending_analysis["enabled_types"],
            progress_callback=self._queue_progress,
            logger=self.logger,
        )
        self.ui_queue.put(("analysis_done", summary))

    def _start_backup(self) -> None:
        if self.is_busy or self._closing:
            return
        if not self.current_summary:
            messagebox.showinfo(_("Backup"), _("Press Analyze first."))
            return

        dry_run = self.dry_run_var.get()
        title, body = build_confirmation(
            self.current_summary, self.duplicate_var.get(), self.verify_var.get(), dry_run
        )
        if not messagebox.askyesno(title, body):
            return

        self._save_settings()
        self.pending_backup = {
            "items": list(self.current_summary.items),
            "source": str(self.current_summary.source_dir),
            "destination": str(self.current_summary.backup_root),
            "duplicate_policy": self._selected_duplicate_policy(),
            "verify_mode": self._selected_verify_mode(),
            "dry_run": dry_run,
            "retry": None,
        }
        self._set_busy(True, _("Starting dry run...") if dry_run else _("Starting backup..."))
        self._run_worker(self._backup_worker)

    def _backup_worker(self) -> None:
        result = execute_backup(
            items=self.pending_backup["items"],
            duplicate_policy=self.pending_backup["duplicate_policy"],
            dry_run=self.pending_backup["dry_run"],
            verify_mode=self.pending_backup["verify_mode"],
            progress_callback=self._queue_progress,
            logger=self.logger,
            cancel_event=self.cancel_event,
        )
        if not result.dry_run:
            if self._record_backup_session(result) is None:
                self.ui_queue.put(("record_warning", _("Backup finished, but Job Results could not be saved.")))
        self.ui_queue.put(("backup_done", result))
        if not result.dry_run and self.pending_backup["retry"] is None:
            # The folders now exist: refresh the "new" markers in the previews.
            try:
                rows, lines = build_preview(
                    self.pending_backup["items"], Path(self.pending_backup["destination"])
                )
            except (OSError, ValueError):
                return
            self.ui_queue.put(("preview_refresh", self.pending_backup["destination"], rows, lines))

    def _cancel_task(self) -> None:
        if self.is_busy and not self.is_analyzing:
            self.cancel_event.set()
            self.status_var.set(stopping_status())
            self._update_button_states()

    def _request_close(self) -> None:
        if self._closing:
            return
        if not self.is_busy and not (self.worker_thread and self.worker_thread.is_alive()):
            self.destroy()
            return
        if not messagebox.askyesno(
            _("Close NDEX One"),
            _(
                "A task is running. Stop after the current file and close when its results are saved?\n\n"
                "An active analysis must finish before the window closes."
            ),
        ):
            return
        self._closing = True
        self.cancel_event.set()
        self.status_var.set(_("Closing safely. Waiting for the running task and its results..."))
        self._update_button_states()

    def _open_in_image_manager(self, destination: str | None = None) -> None:
        destination = self.destination_var.get().strip() if destination is None else destination
        if not destination or not Path(destination).is_dir():
            messagebox.showerror(_("Missing Folder"), _("Backup destination does not exist."))
            return
        launched = launch_app("image_manager", ["--open", "--source", destination])
        if not launched:
            messagebox.showerror(
                _("Handoff"),
                _("Could not find NDEX Image Manager. Build or install it first."),
            )

    def _open_job_results(self, select: Path | None = None) -> None:
        """Show what recent backups copied, skipped, or failed on."""
        from ndex_common.report_dialog import open_job_reports

        open_job_reports(
            self,
            title=NDEX_ONE_TITLE,
            apps=("ndex_one",),
            retry=self._retry_backup,
            select=select,
        )

    def _retry_backup(self, plan) -> None:
        """Back up the files an earlier job failed on, into the same destination.

        The folders come from that job's manifest, not from the form: the
        window may be showing a different pair by now.
        """
        if self.is_busy or self._closing:
            messagebox.showinfo(
                NDEX_ONE_TITLE, _("Wait for the running job to finish, then retry.")
            )
            return
        if not plan.report.destination:
            messagebox.showerror(
                _("Invalid Destination"), _("That job did not record a backup destination.")
            )
            return
        destination = Path(plan.report.destination)
        if not self._destination_usable(destination):
            return

        self.pending_backup = {
            "items": [],
            "source": plan.report.source,
            "destination": plan.report.destination,
            "duplicate_policy": self._selected_duplicate_policy(),
            "verify_mode": self._selected_verify_mode(),
            "dry_run": self.dry_run_var.get(),
            "retry": plan,
        }
        if self.pending_backup["dry_run"]:
            status = _("Rehearsing {files}...")
        else:
            status = _("Retrying {files}...")
        self._set_busy(True, status.format(files=_files(len(plan.paths))))
        self._run_worker(self._retry_worker)

    def _retry_worker(self) -> None:
        # Work out where the files belong, then back them up the ordinary way.
        plan = self.pending_backup["retry"]
        items, _counts = build_scan_items(
            list(plan.paths),
            Path(plan.report.destination),
            self.metadata_extractor,
            progress_callback=self._queue_progress,
            logger=self.logger,
        )
        self.pending_backup["items"] = items
        self._backup_worker()

    def _open_backup_folder(self, destination: str | None = None) -> None:
        destination = Path(self.destination_var.get() if destination is None else destination)
        if destination.exists():
            os.startfile(destination)  # type: ignore[attr-defined]
        else:
            messagebox.showerror(_("Missing Folder"), _("Backup destination does not exist."))

    def _run_worker(self, target) -> None:
        self.cancel_event.clear()
        self._last_progress_at = 0.0
        self._update_button_states()
        self.worker_thread = threading.Thread(target=lambda: self._worker_wrapper(target), daemon=False)
        self.worker_thread.start()

    def _worker_wrapper(self, target) -> None:
        try:
            target()
        except Exception as exc:  # pragma: no cover - UI/runtime specific
            self.ui_queue.put(("error", str(exc)))

    def _display_log_line(self, level: str, message: str) -> str | None:
        job = getattr(self, "pending_backup", None) or {}
        return format_display_line(
            level,
            message,
            destination=job.get("destination"),
            verify_mode=job.get("verify_mode"),
        )

    def _queue_log(self, line: str) -> None:
        self.ui_queue.put(("log", line))

    def _queue_progress(self, stage: str, current: int, total: int, name: str) -> None:
        now = time.monotonic()
        if current != total and now - self._last_progress_at < 0.1:
            return
        self._last_progress_at = now
        self.ui_queue.put(("progress", stage, current, total, name))

    def _process_ui_queue(self) -> None:
        # Yield to input/paint events even when a fast job fills the queue.
        for _turn in range(100):
            try:
                item = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            kind = item[0]
            if kind == "log":
                self.log_text.insert("end", item[1] + "\n")
                self.log_text.see("end")
            elif kind == "progress":
                _kind, stage, current, total, name = item
                progress = 0 if total == 0 else (current / total) * 100
                self.progress_var.set(progress)
                if not self.cancel_event.is_set() and not self._closing:
                    self.status_var.set(self._progress_text(stage, current, total, name))
            elif kind == "analysis_done":
                summary = item[1]
                job = self.pending_analysis
                if (same_folder(summary.source_dir, self.source_var.get().strip())
                        and same_folder(summary.backup_root, self.destination_var.get().strip())
                        and job["enabled_types"] == self._selected_types()):
                    self.current_summary = summary
                    self._render_summary()
                    self._set_busy(False, self._analysis_done_status(summary))
                else:
                    self.current_summary = None
                    self._set_busy(False, _("Inputs changed. Press Analyze again."))
            elif kind == "backup_done":
                result = item[1]
                status = build_completion_status(result)
                self._render_backup_result(result)
                # A finished run stays at 100%; a stopped one keeps where it got to.
                self._set_busy(False, status, progress=None if result.cancelled else 100.0)
                if self._closing or result.dry_run or result.cancelled:
                    pass
                elif result.verification_failed or result.errors:
                    if messagebox.askyesno(
                        _("Backup Warnings"),
                        _(
                            "{failed} file(s) failed verification and "
                            "{errors} total error(s) occurred.\n\n"
                            "Failed files were NOT written to the backup destination, "
                            "so existing backups are untouched.\n\n"
                            "Open Job Results now? Use Retry Failed there to run just "
                            "those files again."
                        ).format(failed=result.verification_failed, errors=result.errors),
                    ):
                        self._open_job_results()
                elif result.total:
                    self._show_completion_dialog(status)
            elif kind == "preview_refresh":
                _kind, destination, rows, lines = item
                if self.current_summary is not None and same_folder(
                    self.current_summary.backup_root, destination
                ):
                    self._render_preview(rows, lines)
            elif kind == "error":
                self._closing = False
                self._set_busy(False, item[1])
                messagebox.showerror(_("Error"), item[1])
            elif kind == "record_warning":
                self._closing = False
                messagebox.showwarning(_("Job Results"), item[1])

        if (self._closing and not self.is_busy and self.ui_queue.empty()
                and not (self.worker_thread and self.worker_thread.is_alive())):
            self.destroy()
            return
        self.after(100, self._process_ui_queue)

    def _render_summary(self) -> None:
        summary = self.current_summary
        total = len(summary.items)
        span = format_day_span(summary.date_range)
        lines = [
            _("Source: {path}").format(path=summary.source_dir),
            _("Destination: {path}").format(path=summary.backup_root),
            _("Total: {files} ({size})").format(files=_files(total), size=format_size(summary.total_size)),
            _("Files: {types}").format(types=format_type_counts(summary.counts)),
            _("Dates: {span}").format(span=span) if span else _("Dates: No supported files found"),
        ]
        if summary.free_space is not None:
            lines.append(
                _("Free space at destination: {size}").format(size=format_size(summary.free_space))
            )
        for note in (
            free_space_warning(summary.total_size, summary.free_space),
            fallback_note(summary.fallback_count),
        ):
            if note:
                lines.append(note)
        lines.append(_("Log File: {path}").format(path=self.logger.log_path))
        summary_text = "\n".join(lines)
        self._summary_text = summary_text
        self.summary_var.set(summary_text)
        self.rule_var.set(example_folder_text(summary))
        self._render_preview(summary.preview_rows, summary.folder_tree_lines)

    def _render_preview(self, preview_rows, folder_tree_lines) -> None:
        for row_id in self.preview_treeview.get_children():
            self.preview_treeview.delete(row_id)
        for row in preview_rows:
            self.preview_treeview.insert(
                "",
                "end",
                values=(
                    row.date_label,
                    row.folder_rel_path.as_posix(),
                    format_type_counts(row.type_counts),
                    preview_status_label(row.status),
                ),
            )

        self.folder_preview.delete("1.0", "end")
        self.folder_preview.insert("1.0", "\n".join(folder_tree_lines))
        self.folder_preview.see("1.0")

    def _progress_text(self, stage: str, current: int, total: int, name: str) -> str:
        if stage == "analyze":
            return _("Analyzing {current}/{total}: {name} — {detail}").format(
                current=current, total=total, name=name, detail=analyzing_suffix()
            )
        if self.pending_backup and self.pending_backup.get("dry_run"):
            template = _("Checking {current}/{total}: {name}")
        else:
            template = _("Copying {current}/{total}: {name}")
        return template.format(current=current, total=total, name=name)

    def _analysis_done_status(self, summary) -> str:
        count = len(summary.items)
        if not count:
            return _("Analysis done: no supported files found in the source folder.")
        return _(
            "Analysis done: {files} ready to copy. Press Start Backup when you are ready."
        ).format(files=_files(count))

    def _show_completion_dialog(self, status: str) -> None:
        """A small "all done" dialog with the next steps a photographer wants."""
        # A retry uses its recorded destination even if the form shows another job.
        destination = (self.pending_backup or {}).get("destination", self.destination_var.get().strip())
        dialog = tk.Toplevel(self)
        dialog.title(NDEX_ONE_TITLE)
        dialog.transient(self)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=20, style="Card.TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=_("Backup complete"), style="CardSection.TLabel").pack(anchor="w")
        ttk.Label(frame, text=status, style="Card.TLabel", wraplength=380, justify="left").pack(
            anchor="w", pady=(6, 14)
        )
        ttk.Label(frame, text=_("Destination: {path}").format(path=destination), style="CardMuted.TLabel",
                  wraplength=380, justify="left").pack(anchor="w", pady=(0, 14))
        row = ttk.Frame(frame, style="CardInner.TFrame")
        row.pack(fill="x")

        def run(command) -> None:
            dialog.destroy()
            command()

        ttk.Button(
            row, text=_("Open Backup Folder"),
            command=lambda: run(lambda: self._open_backup_folder(destination)),
        ).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(
            row, text=_("Open in Image Manager"),
            command=lambda: run(lambda: self._open_in_image_manager(destination)),
        ).pack(
            side="left", padx=(0, 6)
        )
        close = ttk.Button(row, text=_("Close"), style="Accent.TButton", command=dialog.destroy)
        close.pack(side="right")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.bind("<Return>", lambda _e: dialog.destroy())
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_reqheight()) // 2
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        close.focus_set()
        dialog.grab_set()
        self.wait_window(dialog)

    def _record_backup_session(self, result) -> Path | None:
        from ndex_common.workflow import record_backup

        # The folders the job actually used. The form can have changed since
        # Analyze, and a manifest with the wrong destination misleads a retry.
        job = self.pending_backup
        plan = job["retry"]
        return record_backup(
            job["source"],
            job["destination"],
            result,
            context=plan.context() if plan is not None else None,
        )

    def _render_backup_result(self, result) -> None:
        if result.dry_run:
            first = _("Dry run result (nothing was copied): {copied} of {total} would be copied")
        else:
            first = _("Backup result: {copied} of {total} copied")
        lines = [
            first.format(copied=result.copied, total=result.total),
            _("  Verified {verified} · Verify failed {failed}").format(
                verified=result.verified, failed=result.verification_failed
            ),
            _("  Skipped {skipped} · Overwritten {overwritten} · Errors {errors}").format(
                skipped=result.skipped, overwritten=result.overwritten, errors=result.errors
            ),
        ]
        if result.cancelled:
            lines.append(_("  Stopped early; {count} files not run.").format(count=not_run_count(result)))
        self.summary_var.set(self._summary_text + "\n\n" + "\n".join(lines))

    def _set_busy(self, busy: bool, status: str, progress: float | None = 0.0) -> None:
        """Switch between working and idle. ``progress`` is the bar value once idle
        (None leaves it where it is)."""
        self.is_busy = busy
        self.status_var.set(status)
        if not busy:
            self.is_analyzing = False
            if progress is not None:
                self.progress_var.set(progress)
        self._update_button_states()

    def _update_button_states(self) -> None:
        has_paths = bool(self.source_var.get().strip()) and bool(self.destination_var.get().strip())
        has_analysis = self.current_summary is not None

        blocked = self.is_busy or self._closing
        for control in self._input_controls:
            control.state(["disabled"] if blocked else ["!disabled"])
        self.analyze_button.config(state="disabled" if blocked or not has_paths else "normal")
        self.backup_button.config(state="disabled" if blocked or not has_analysis else "normal")
        # One accent button at a time: the next step the user should take.
        self.analyze_button.config(style="TButton" if has_analysis else "Accent.TButton")
        self.backup_button.config(style="Accent.TButton" if has_analysis else "TButton")
        self.cancel_button.config(
            state="normal" if self.is_busy and not self.is_analyzing and not self.cancel_event.is_set() else "disabled"
        )
        destination_ready = (
            "disabled" if self.is_busy or not self.destination_var.get().strip() else "normal"
        )
        self.open_button.config(state=destination_ready)
        self.handoff_button.config(state=destination_ready)


def run_app(
    initial_source: Path | None = None,
    initial_destination: Path | None = None,
    preload_only: bool = False,
    retry_manifest: Path | None = None,
) -> None:
    app = DSBApp(
        initial_source=initial_source,
        initial_destination=initial_destination,
        preload_only=preload_only,
        retry_manifest=retry_manifest,
    )
    app.mainloop()
