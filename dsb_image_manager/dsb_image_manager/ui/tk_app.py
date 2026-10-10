from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from src.branding import NDEX_IMAGE_MANAGER_TITLE

from ..core.models import ExportOptions, ImageRecord
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
    apply_tk_theme,
    apply_window_icon,
    build_app_header,
    style_text_widget,
)

SETTINGS_SECTION = "image_manager"

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
    "name": {"label": "File", "sort_key": "file_name", "width": 260},
    "type": {"label": "Type", "sort_key": "media_type", "width": 58},
    "pick": {"label": "Pick", "sort_key": "pick_status", "width": 82},
    "rating": {"label": "Rating", "sort_key": "rating", "width": 70},
    "date": {"label": "Capture Date", "sort_key": "capture_datetime", "width": 158},
}


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
        self.records: list[ImageRecord] = []
        self.current_record: ImageRecord | None = None
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

        self.file_filter = tk.StringVar(value="all")
        self.pick_filter = tk.StringVar(value="all")
        self.sort_key = tk.StringVar(value="capture_datetime")
        self.sort_descending = tk.BooleanVar(value=False)
        self.detail_mode = tk.StringVar(value="Simple")
        self.image_layout = tk.StringVar(value="50%")
        self.preview_background = tk.StringVar(value="Dark Gray")
        self.status = tk.StringVar(value="Choose a shooting folder to begin.")
        self.selection_status = tk.StringVar(value="0 selected")
        self.folder_status = tk.StringVar(value="No folder selected")
        self.catalog_status = tk.StringVar(value="0 images")
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
        file_menu.add_command(label="Choose Folder...", accelerator="Ctrl+O", command=self.choose_folder)
        file_menu.add_command(label="Reopen Last Folder", command=self.reopen_last_folder)
        file_menu.add_command(label="Rescan", accelerator="F5", command=self.rescan)
        file_menu.add_separator()
        file_menu.add_command(label="Export Selected...", accelerator="Ctrl+E", command=self.open_export_dialog)
        file_menu.add_command(label="Backup Picked...", command=self.backup_picked)
        file_menu.add_command(label="Export XMP Sidecars (Picked/Rated)", command=self.export_xmp_sidecars)
        file_menu.add_command(label="Send to Auto Selector...", command=self.send_to_auto_selector)
        file_menu.add_command(label="Send Picks to Frame...", command=self.send_picks_to_frame)
        file_menu.add_separator()
        file_menu.add_command(label="Job Results...", command=self.open_job_results)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        self.file_menu = file_menu
        self._file_action_indices = [
            index for index in range(file_menu.index("end") + 1)
            if file_menu.type(index) == "command"
            and file_menu.entrycget(index, "label") not in {"Exit", "Job Results..."}
        ]
        menu_bar.add_cascade(label="File", menu=file_menu)

        selection_menu = tk.Menu(menu_bar, tearoff=0)
        selection_menu.add_command(label="Select All Visible", accelerator="Ctrl+A", command=self.select_all_visible)
        selection_menu.add_command(label="Fullscreen Preview", accelerator="F", command=self.open_fullscreen_viewer)
        menu_bar.add_cascade(label="Selection", menu=selection_menu)

        filter_menu = tk.Menu(menu_bar, tearoff=0)
        type_menu = tk.Menu(filter_menu, tearoff=0)
        for value in ("all", "jpg", "raw", "paired", "raw_only", "jpg_only", "proxy_failed"):
            type_menu.add_radiobutton(
                label=value,
                variable=self.file_filter,
                value=value,
                command=self.refresh_records,
            )
        pick_menu = tk.Menu(filter_menu, tearoff=0)
        for value in ("all", "Unrated", "Pick", "Maybe", "Reject"):
            pick_menu.add_radiobutton(
                label=value,
                variable=self.pick_filter,
                value=value,
                command=self.refresh_records,
            )
        filter_menu.add_cascade(label="Type", menu=type_menu)
        filter_menu.add_cascade(label="Pick", menu=pick_menu)
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
        info.pack(side=tk.RIGHT)
        ttk.Label(info, textvariable=self.folder_status, style="Muted.TLabel").pack(anchor=tk.E)
        ttk.Label(info, textvariable=self.catalog_status, style="Muted.TLabel").pack(anchor=tk.E)

        toolbar_outer = ttk.Frame(self, padding=(16, 0, 16, 10))
        toolbar_outer.pack(fill=tk.X)
        toolbar = ttk.Frame(toolbar_outer, padding=(12, 8), style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X)

        self.choose_button = ttk.Button(toolbar, text="Choose Folder", command=self.choose_folder)
        self.choose_button.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(toolbar, text="Type", style="Toolbar.TLabel").pack(side=tk.LEFT)
        file_filter = ttk.Combobox(
            toolbar,
            textvariable=self.file_filter,
            values=("all", "jpg", "raw", "paired", "raw_only", "jpg_only", "proxy_failed"),
            width=14,
            state="readonly",
        )
        file_filter.pack(side=tk.LEFT, padx=(6, 14))
        file_filter.bind("<<ComboboxSelected>>", lambda event: self.refresh_records())
        self.file_filter_widget = file_filter

        ttk.Label(toolbar, text="Pick", style="Toolbar.TLabel").pack(side=tk.LEFT)
        pick_filter = ttk.Combobox(
            toolbar,
            textvariable=self.pick_filter,
            values=("all", "Unrated", "Pick", "Maybe", "Reject"),
            width=10,
            state="readonly",
        )
        pick_filter.pack(side=tk.LEFT, padx=(6, 14))
        pick_filter.bind("<<ComboboxSelected>>", lambda event: self.refresh_records())
        self.pick_filter_widget = pick_filter

        ttk.Label(
            toolbar,
            text="File menu: exports and backup | Click columns to sort",
            style="CardMuted.TLabel",
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))

        self.left_pane = ttk.Frame(self.paned, padding=0, style="Card.TFrame")
        self.paned.add(self.left_pane, weight=1)
        self.right_pane = ttk.Frame(self.paned, padding=0, style="Card.TFrame")
        self.paned.add(self.right_pane, weight=1)

        columns = tuple(TREE_COLUMNS.keys())
        self.tree = ttk.Treeview(self.left_pane, columns=columns, show="headings", selectmode="extended")
        for column in columns:
            self.tree.heading(column, text=TREE_COLUMNS[column]["label"], command=lambda name=column: self.sort_by_column(name))
            self.tree.column(column, width=TREE_COLUMNS[column]["width"], anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=(0, 1), pady=0)
        scrollbar = ttk.Scrollbar(self.left_pane, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(fill=tk.Y, side=tk.LEFT)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.tag_configure("Pick", background="#e7f7e8")
        self.tree.tag_configure("Maybe", background="#fff7df")
        self.tree.tag_configure("Reject", background="#fde7e7")

        preview_frame = tk.Frame(self.right_pane, bg=self._preview_background_color(), bd=0, highlightthickness=0)
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
        )
        self.preview_label.pack(fill=tk.BOTH, expand=True)
        self.preview_label.bind("<Double-Button-1>", lambda event: self.open_fullscreen_viewer())
        self.preview_label.bind("<Configure>", lambda event: self._schedule_preview_refresh())

        self.details_frame = tk.Frame(self.right_pane, bg=CARD_BG, bd=0, highlightthickness=0)
        self.details_frame.pack(fill=tk.X, pady=(1, 0))

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
        )
        self.summary_label.pack(fill=tk.X, padx=12, pady=(0, 8))

        rating_row = tk.Frame(self.details_frame, bg=CARD_BG, bd=0, highlightthickness=0)
        rating_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        tk.Label(
            rating_row,
            text="Rating",
            bg=CARD_BG,
            fg=TEXT_MUTED,
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(0, 8))
        for rating in range(1, 6):
            star = tk.Label(
                rating_row,
                text=STAR_EMPTY,
                font=("Segoe UI Symbol", 18),
                cursor="hand2",
                padx=2,
                bg=CARD_BG,
                fg="#6b7280",
                bd=0,
                highlightthickness=0,
            )
            star.pack(side=tk.LEFT)
            star.bind("<Button-1>", lambda event, value=rating: self.set_rating(value))
            self.star_labels.append(star)
        ttk.Button(rating_row, text="Clear", command=lambda: self.set_rating(0)).pack(side=tk.LEFT, padx=(10, 0))

        self.detail_text = tk.Text(
            self.details_frame,
            height=8,
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
        self.detail_text.pack(fill=tk.X, padx=0, pady=(0, 10))
        style_text_widget(self.detail_text)
        self.detail_text.configure(state=tk.DISABLED)

        bottom = ttk.Frame(self, padding=(16, 0, 16, 12), style="Footer.TFrame")
        bottom.pack(fill=tk.X)
        status_row = ttk.Frame(bottom, style="Footer.TFrame")
        status_row.pack(fill=tk.X, pady=(0, 4))
        self.cancel_button = ttk.Button(status_row, text="Cancel", command=self.cancel_work, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.work_progress = ttk.Progressbar(status_row, length=130, mode="determinate")
        self.work_progress.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Label(status_row, textvariable=self.status, style="Muted.TLabel", anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(bottom, textvariable=self.selection_status, style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            bottom,
            text="F fullscreen | P/M/X/U pick | 0-5 rating",
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)
        self.after(100, self.apply_layout_preset)
        self.after(120, self.apply_preview_background)

    def _bind_shortcuts(self) -> None:
        self.bind("<p>", lambda event: self.set_pick("Pick"))
        self.bind("<P>", lambda event: self.set_pick("Pick"))
        self.bind("<m>", lambda event: self.set_pick("Maybe"))
        self.bind("<M>", lambda event: self.set_pick("Maybe"))
        self.bind("<x>", lambda event: self.set_pick("Reject"))
        self.bind("<X>", lambda event: self.set_pick("Reject"))
        self.bind("<u>", lambda event: self.set_pick("Unrated"))
        self.bind("<U>", lambda event: self.set_pick("Unrated"))
        for value in range(0, 6):
            self.bind(str(value), lambda event, rating=value: self.set_rating(rating))
        self.bind("<Down>", lambda event: self.move_selection(1))
        self.bind("<Right>", lambda event: self.move_selection(1))
        self.bind("<Up>", lambda event: self.move_selection(-1))
        self.bind("<Left>", lambda event: self.move_selection(-1))
        self.bind("<f>", lambda event: self.open_fullscreen_viewer())
        self.bind("<F>", lambda event: self.open_fullscreen_viewer())
        self.bind("<Control-a>", lambda event: self.select_all_visible())
        self.bind("<Control-o>", lambda event: self.choose_folder())
        self.bind("<Control-e>", lambda event: self.open_export_dialog())
        self.bind("<F5>", lambda event: self.rescan())

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
        self.status.set(f"Scanning {self.source_dir} ...")
        self.tree.delete(*self.tree.get_children())
        self.records = []
        self.current_record = None
        self._show_preview(None)
        self._show_details(None)
        self._refresh_rating_widgets(0)
        self.update_selection_status()
        self.update_catalog_status()
        source = self.source_dir
        self._start_worker("scan", lambda cancel, progress: ImageScanner().scan(
            source, recursive=True, progress_callback=progress, cancel_event=cancel,
        ))

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
        self.cancel_button.configure(state=tk.NORMAL if busy else tk.DISABLED)
        if busy:
            self.work_progress.configure(mode="indeterminate", value=0)
            self.work_progress.start(15)
        else:
            self.work_progress.stop()
            self.work_progress.configure(mode="determinate", value=0)

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
            except ScanCancelled:
                cancelled = True
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
        if kind == "work_progress":
            _, _generation, index, total, name = event
            if index > 0:
                self.work_progress.stop()
                self.work_progress.configure(mode="determinate", maximum=max(total, 1), value=index)
            if not self._cancel_event.is_set():
                self.status.set(f"{self._active_job.title()} {index}/{total}: {name}")
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
                self.status.set(f"{task.title()} failed.")
                messagebox.showerror(f"{task.title()} failed", error)
            elif task == "scan":
                if cancelled:
                    self.status.set("Scan cancelled. Previous catalog was preserved; rescan to reload.")
                else:
                    self._scan_finished(result.catalog_path)
            else:
                self._operation_finished(task, *result)
        return True

    def _scan_finished(self, catalog_path: Path) -> None:
        if self.catalog:
            self.catalog.close()
        self.catalog = Catalog(catalog_path)
        self.refresh_records()
        self.status.set(f"Ready. Catalog: {catalog_path}")

    def refresh_records(self) -> None:
        if not self.catalog:
            return
        selection = self.tree.selection()
        focus = self.tree.focus()
        self.records = self.catalog.list_images(
            file_filter=self.file_filter.get(),
            pick_filter=self.pick_filter.get(),
            sort_key=self.sort_key.get(),
            descending=self.sort_descending.get(),
        )
        self.tree.delete(*self.tree.get_children())
        self.current_record = None
        self._update_column_headings()
        for record in self.records:
            values = (
                record.display_name,
                record.file_ext.upper(),
                record.pick_status,
                _rating_text(record.rating),
                record.effective_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            )
            self.tree.insert("", tk.END, iid=str(record.id), values=values, tags=(record.pick_status,))
        if self.records:
            first = self.tree.get_children()[0]
            surviving = [iid for iid in selection if self.tree.exists(iid)]
            self.tree.selection_set(surviving or [first])
            focused = focus if focus in surviving else (surviving[0] if surviving else first)
            self.tree.focus(focused)
            self.tree.see(focused)
            self.on_select()
        else:
            self.status.set("No images match the current filters.")
            self._show_preview(None)
            self._show_details(None)
            self._refresh_rating_widgets(0)
        self.update_selection_status()
        self.update_catalog_status()

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
            if config["sort_key"] == current_sort:
                label = f"{label} {SORT_DESC if self.sort_descending.get() else SORT_ASC}"
            self.tree.heading(column, text=label, command=lambda name=column: self.sort_by_column(name))

    def update_catalog_status(self) -> None:
        folder = self.source_dir.name if self.source_dir else "No folder selected"
        self.folder_status.set(folder)
        self.catalog_status.set(
            f"{len(self.records)} visible | filter: {self.file_filter.get()} / {self.pick_filter.get()}"
        )

    def on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            self.update_selection_status()
            return
        focused = self.tree.focus()
        image_id = int(focused if focused in selected else selected[-1])
        record = next((item for item in self.records if item.id == image_id), None)
        self.current_record = record
        self._show_preview(record)
        self._show_details(record)
        self._refresh_rating_widgets(record.rating if record else 0)
        self.update_selection_status()

    def set_pick(self, pick_status: str) -> None:
        if not self._can_start_work():
            return
        if not self.catalog or not self.current_record or self.current_record.id is None:
            return
        targets = [record for record in self.selected_records() if record.id is not None]
        self.catalog.update_selections((record.id for record in targets), pick_status=pick_status)
        self.refresh_records()

    def set_rating(self, rating: int) -> None:
        if not self._can_start_work():
            return
        if not self.catalog or not self.current_record or self.current_record.id is None:
            return
        targets = [record for record in self.selected_records() if record.id is not None]
        self.catalog.update_selections((record.id for record in targets), rating=rating)
        self._refresh_rating_widgets(rating)
        self.refresh_records()

    def move_selection(self, offset: int) -> None:
        children = list(self.tree.get_children())
        if not children:
            return
        selected = self.tree.selection()
        index = children.index(selected[0]) if selected else 0
        next_index = max(0, min(len(children) - 1, index + offset))
        next_item = children[next_index]
        self.tree.selection_set(next_item)
        self.tree.focus(next_item)
        self.tree.see(next_item)
        self.on_select()

    def select_all_visible(self) -> str:
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children)
            self.tree.focus(children[0])
            self.on_select()
        return "break"

    def selected_records(self) -> list[ImageRecord]:
        selected_ids = {int(item_id) for item_id in self.tree.selection()}
        selected = [record for record in self.records if record.id in selected_ids]
        if selected:
            return selected
        return [self.current_record] if self.current_record else []

    def update_selection_status(self) -> None:
        selected_count = len(self.tree.selection())
        total_count = len(self.records)
        self.selection_status.set(f"{selected_count} selected / {total_count} visible")

    def show_shortcuts(self) -> None:
        messagebox.showinfo(
            "Shortcuts",
            "Arrows: move selection\n"
            "F: fullscreen\n"
            "P/M/X/U: Pick / Maybe / Reject / Unrated\n"
            "0-5: rating\n"
            "Ctrl+A: select all visible\n"
            "Ctrl+O: choose folder\n"
            "Ctrl+E: export selected\n"
            "F5: rescan",
        )

    def backup_picked(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Scan a folder first.")
            return
        records = self.catalog.list_images(pick_filter="Pick")
        if not records:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "No picked images found. Set Pick first.")
            return
        destination = filedialog.askdirectory(title="Choose NDEX backup destination")
        if not destination:
            return
        self._start_operation("backup", records, Path(destination))

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
        self.status.set(f"Starting {kind} for {len(snapshots)} image(s)...")

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
        count = getattr(summary, "copied", getattr(summary, "exported", getattr(summary, "written", 0)))
        message = f"Completed {count} / skipped {summary.skipped} / failed or not run {summary.errors}"
        self.status.set(f"{kind.title()} {finished}. {message}")
        details = [message]
        if summary.cancelled:
            details.append("The active file finished safely. Unprocessed files are listed in Job Results.")
        elif kind == "xmp" and summary.written == 0 and summary.errors == 0:
            details.append("No picked or rated images found. Set pick status or rating first.")
        details.extend(summary.messages[:10])
        details.extend(warnings)
        show = messagebox.showwarning if summary.errors or warnings else messagebox.showinfo
        show(f"{kind.title()} {finished}", "\n\n".join(details))

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
        records = self.catalog.list_images(pick_filter="Pick")
        files = frame_ready_paths(
            record.file_path
            for record in records
            if record.media_type == "jpg" and Path(record.file_path).suffix.casefold() in (".jpg", ".jpeg")
        )
        if not files:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "No picked JPG files to send to Auto Selector.")
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

    def send_picks_to_frame(self) -> None:
        if not self._can_start_work():
            return
        if not self.catalog:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Scan a folder first.")
            return
        from ndex_common.manifest import frame_ready_paths
        from ndex_common.workflow import record_select_handoff

        records = self.catalog.list_images(pick_filter="Pick")
        files = frame_ready_paths(record.file_path for record in records if record.media_type == "jpg")
        if not files:
            files = frame_ready_paths(record.file_path for record in records)
        if not files:
            messagebox.showinfo(
                NDEX_IMAGE_MANAGER_TITLE,
                "No picked JPG/PNG/TIFF files to send. Frame does not import RAW.",
            )
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
        records = self.selected_records()
        if not records:
            messagebox.showinfo(NDEX_IMAGE_MANAGER_TITLE, "Select one or more images first.")
            return

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
            text=f"Export {len(records)} selected image(s)",
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
                self.details_frame.pack(fill=tk.X, pady=(8, 0))
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
        self.paned.sashpos(0, max(220, left_width))

    def open_fullscreen_viewer(self) -> None:
        record = self.current_record
        if not record:
            return

        viewer = tk.Toplevel(self)
        viewer.title(record.display_name)
        fullscreen_bg = self._preview_background_color()
        fullscreen_fg = "#111827" if self.preview_background.get() == "Light Gray" else "#d7dee8"
        fullscreen_muted = "#374151" if self.preview_background.get() == "Light Gray" else "#9fb0c4"
        viewer.configure(bg=fullscreen_bg)
        viewer.attributes("-fullscreen", True)

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
            star.bind("<Button-1>", lambda event, value=rating: set_fullscreen_rating(value))
            fullscreen_stars.append(star)

        tk.Button(controls, text="Clear", command=lambda: set_fullscreen_rating(0), width=8).pack(side=tk.LEFT, padx=(8, 18))
        tk.Label(
            controls,
            text="Left/Right: move   0-5: rating   P/M/X/U: pick   Esc/F/double-click: close",
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
            viewer.title(current.display_name)
            metadata_label.configure(text=self._fullscreen_detail_text(current))
            _refresh_star_labels(fullscreen_stars, current.rating)
            if not image_path or not image_path.exists():
                image_label.configure(image="", text="Preview unavailable")
                return
            try:
                with Image.open(image_path) as image:
                    image = ImageOps.exif_transpose(image)
                    max_size = (max(viewer.winfo_width(), 640), max(viewer.winfo_height() - 104, 480))
                    image.thumbnail(max_size)
                    self.fullscreen_image = ImageTk.PhotoImage(image)
                    image_label.configure(image=self.fullscreen_image, text=current.display_name)
            except OSError:
                image_label.configure(image="", text="Preview unavailable")

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

        def set_fullscreen_rating(rating: int) -> None:
            self.set_rating(rating)
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
            self.preview_label.configure(image="", text="Preview unavailable")
            self.preview_image = None
            return
        try:
            with Image.open(image_path) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail(self._preview_max_size())
                self.preview_image = ImageTk.PhotoImage(image)
                self.preview_label.configure(image=self.preview_image, text="")
        except OSError:
            self.preview_label.configure(image="", text="Preview unavailable")
            self.preview_image = None

    def _preview_max_size(self) -> tuple[int, int]:
        width = max(self.preview_label.winfo_width() - 24, 640)
        height = max(self.preview_label.winfo_height() - 24, 420)
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

    def _simple_detail_lines(self, record: ImageRecord) -> list[str]:
        return [
            f"File: {record.display_name}",
            f"Capture: {record.effective_datetime:%Y-%m-%d %H:%M:%S}",
            f"Camera: {record.camera_model or '-'}",
            f"Lens: {record.lens_model or '-'}",
            f"Exposure: {record.exposure_time or '-'} / f/{record.aperture or '-'} / ISO {record.iso or '-'}",
            f"Selection: {record.pick_status} / Rating: {_rating_text(record.rating)}",
        ]

    def _full_detail_lines(self, record: ImageRecord) -> list[str]:
        return [
                f"Path: {record.file_path}",
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
                f"Selection: {record.pick_status} / Rating: {_rating_text(record.rating)}",
                f"Note: {record.note or '-'}",
        ]

    def _fullscreen_detail_text(self, record: ImageRecord) -> str:
        return (
            f"{record.display_name}   {_rating_text(record.rating)}   {record.pick_status}\n"
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
    return STAR_EMPTY if rating <= 0 else STAR_FILLED * rating


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
