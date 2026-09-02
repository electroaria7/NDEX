from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .backup_executor import execute_backup
from .app_paths import get_user_data_dir
from .branding import NDEX_ONE_TITLE
from .config import ConfigManager
from .file_types import FILE_TYPE_ORDER, RAW_BRANDS, get_file_type_definitions, get_file_type_label, get_visible_file_types
from .logger import AppLogger
from .metadata import MetadataExtractor
from .scanner import analyze_source

from ndex_common.launch import launch_app
from ndex_common.theme import apply_tk_theme, apply_window_icon, build_app_header, style_text_widget

VERIFY_MODE_LABELS = {
    "size": "Fast check (file size)",
    "sha256": "Full check (SHA-256, slower)",
    "none": "No verification",
}
VERIFY_LABEL_TO_MODE = {label: mode for mode, label in VERIFY_MODE_LABELS.items()}

DUPLICATE_POLICY_LABELS = {
    "rename": "Rename (keep both)",
    "smart": "Smart skip (identical content)",
    "skip": "Skip (same filename)",
    "overwrite": "Overwrite existing",
}
DUPLICATE_LABEL_TO_POLICY = {label: policy for policy, label in DUPLICATE_POLICY_LABELS.items()}


class DSBApp(tk.Tk):
    def __init__(
        self,
        initial_source: Path | None = None,
        initial_destination: Path | None = None,
        preload_only: bool = False,
    ):
        super().__init__()
        self.title(NDEX_ONE_TITLE)
        self.geometry("1220x820")
        self.minsize(1080, 720)
        self.brand_images: list[tk.PhotoImage] = []
        apply_window_icon(self, self.brand_images)
        apply_tk_theme(self)

        self.root_dir = get_user_data_dir()
        self.config_manager = ConfigManager()
        self.settings = self.config_manager.load()
        self.ui_queue: queue.Queue = queue.Queue()
        self.logger = AppLogger(sink=self._queue_log)
        self.metadata_extractor = MetadataExtractor.from_settings(self.settings)

        self.current_summary = None
        self.worker_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.is_busy = False
        self.pending_analysis: dict | None = None
        self.pending_backup: dict | None = None

        # With preload_only the caller passed the folders to use (NDEX handoff),
        # so remembered folders stay out of the way and "Open Empty" is empty.
        remembered_source = "" if preload_only else self.settings.get("last_source", "")
        remembered_destination = "" if preload_only else self.settings.get("last_destination", "")
        self.source_var = tk.StringVar(value=str(initial_source) if initial_source else remembered_source)
        self.destination_var = tk.StringVar(
            value=str(initial_destination) if initial_destination else remembered_destination
        )
        self.duplicate_var = tk.StringVar(
            value=DUPLICATE_POLICY_LABELS.get(
                self.settings.get("duplicate_policy", "rename"), DUPLICATE_POLICY_LABELS["rename"]
            )
        )
        self.verify_var = tk.StringVar(
            value=VERIFY_MODE_LABELS.get(
                self.settings.get("verify_mode", "size"), VERIFY_MODE_LABELS["size"]
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
        self.status_var = tk.StringVar(value="Select a source and destination folder.")
        self.summary_var = tk.StringVar(value="No analysis yet.")
        self._summary_text = "No analysis yet."
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_layout()
        self._bind_events()
        self._update_button_states()
        self.after(100, self._process_ui_queue)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = build_app_header(
            self,
            title=NDEX_ONE_TITLE,
            tagline="Analyze camera files, preview the folder tree, then run a safe backup.",
            holder=self.brand_images,
        )
        header.grid(row=0, column=0, sticky="ew")

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        left = ttk.Frame(body, padding=16, style="Card.TFrame")
        right = ttk.Frame(body, padding=16, style="Card.TFrame")
        body.add(left, weight=3)
        body.add(right, weight=4)

        for frame in (left, right):
            frame.columnconfigure(1, weight=1)

        ttk.Label(left, text="Source Folder", style="CardSection.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(left, textvariable=self.source_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        ttk.Button(left, text="Browse", command=self._browse_source).grid(row=1, column=2, padx=(8, 0))

        ttk.Label(left, text="Backup Destination", style="CardSection.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.destination_var).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(4, 8)
        )
        ttk.Button(left, text="Browse", command=self._browse_destination).grid(row=3, column=2, padx=(8, 0))

        ttk.Label(left, text="File Types", style="CardSection.TLabel").grid(row=4, column=0, sticky="w", pady=(6, 0))
        types_frame = ttk.Frame(left, style="CardInner.TFrame")
        types_frame.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 8))
        self.brand_frame = ttk.Frame(types_frame, style="CardInner.TFrame")
        self.brand_frame.grid(row=0, column=0, sticky="w")
        for column, (brand_key, brand) in enumerate(RAW_BRANDS.items()):
            ttk.Checkbutton(
                self.brand_frame,
                text=brand["label"],
                variable=self.brand_vars[brand_key],
                command=self._refresh_file_type_options,
                style="Card.TCheckbutton",
            ).grid(row=0, column=column, sticky="w", padx=(0, 12))

        self.types_frame = ttk.Frame(types_frame, style="CardInner.TFrame")
        self.types_frame.grid(row=1, column=0, sticky="w", pady=(6, 0))
        for index, file_type in enumerate(FILE_TYPE_ORDER):
            checkbutton = ttk.Checkbutton(
                self.types_frame,
                text=get_file_type_label(file_type),
                variable=self.type_vars[file_type],
                style="Card.TCheckbutton",
            )
            row = index // 3
            column = index % 3
            checkbutton.grid(row=row, column=column, sticky="w", padx=(0, 12), pady=(2, 0))
            self.type_checkbuttons[file_type] = checkbutton
        self._refresh_file_type_options()

        ttk.Label(left, text="Duplicate Handling", style="CardSection.TLabel").grid(row=6, column=0, sticky="w", pady=(6, 0))
        duplicate_combo = ttk.Combobox(
            left,
            textvariable=self.duplicate_var,
            values=list(DUPLICATE_POLICY_LABELS.values()),
            state="readonly",
        )
        duplicate_combo.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 8))

        ttk.Label(left, text="Copy Verification", style="CardSection.TLabel").grid(row=8, column=0, sticky="w", pady=(6, 0))
        verify_combo = ttk.Combobox(
            left,
            textvariable=self.verify_var,
            values=list(VERIFY_MODE_LABELS.values()),
            state="readonly",
        )
        verify_combo.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(4, 8))

        ttk.Checkbutton(
            left,
            text="Dry Run (preview only, do not copy files)",
            variable=self.dry_run_var,
            style="Card.TCheckbutton",
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(2, 10))

        ttk.Label(left, text="Backup Rule", style="CardSection.TLabel").grid(row=11, column=0, sticky="w")
        ttk.Label(left, text="YYYY / MM / MMDD / file_type", style="CardMuted.TLabel").grid(
            row=12, column=0, columnspan=3, sticky="w", pady=(2, 0)
        )
        ttk.Label(left, text="Example: 2026 / 05 / 0503 / cr3", style="CardMuted.TLabel").grid(
            row=13, column=0, columnspan=3, sticky="w"
        )

        buttons = ttk.Frame(left, style="CardInner.TFrame")
        buttons.grid(row=14, column=0, columnspan=3, sticky="ew", pady=(16, 8))
        for column in range(3):
            buttons.columnconfigure(column, weight=1)
        self.analyze_button = ttk.Button(buttons, text="Analyze Files", command=self._start_analysis)
        self.preview_button = ttk.Button(buttons, text="Preview Tree", command=self._preview_tree)
        self.backup_button = ttk.Button(
            buttons, text="Start Backup", style="Accent.TButton", command=self._start_backup
        )
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self._cancel_task)
        self.open_button = ttk.Button(buttons, text="Open Backup Folder", command=self._open_backup_folder)
        self.handoff_button = ttk.Button(
            buttons, text="Open in Image Manager", command=self._open_in_image_manager
        )
        self.analyze_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.preview_button.grid(row=0, column=1, sticky="ew", padx=6)
        self.backup_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self.cancel_button.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(6, 0))
        self.open_button.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        self.handoff_button.grid(row=1, column=2, sticky="ew", padx=(6, 0), pady=(6, 0))
        ttk.Button(buttons, text="Job Results...", command=self._open_job_results).grid(
            row=2, column=0, sticky="ew", padx=(0, 6), pady=(6, 0)
        )

        progress_frame = ttk.LabelFrame(left, text="Progress", padding=12)
        progress_frame.grid(row=15, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        progress_frame.columnconfigure(0, weight=1)
        ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100).grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.status_var, style="CardMuted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

        right.rowconfigure(3, weight=2)
        right.rowconfigure(5, weight=3)

        ttk.Label(right, text="Summary", style="CardSection.TLabel").grid(row=0, column=0, sticky="w")
        summary_label = ttk.Label(right, textvariable=self.summary_var, justify="left", style="Card.TLabel")
        summary_label.grid(row=1, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(right, text="Date Preview", style="CardSection.TLabel").grid(row=2, column=0, sticky="w")
        columns = ("date", "folder", "files", "status")
        self.preview_treeview = ttk.Treeview(right, columns=columns, show="headings", height=10)
        self.preview_treeview.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        for column, width in zip(columns, (110, 220, 220, 100)):
            self.preview_treeview.heading(column, text=column.title())
            self.preview_treeview.column(column, width=width, anchor="w")
        tree_scroll = ttk.Scrollbar(right, orient="vertical", command=self.preview_treeview.yview)
        tree_scroll.grid(row=3, column=1, sticky="ns", pady=(6, 0))
        self.preview_treeview.configure(yscrollcommand=tree_scroll.set)

        ttk.Label(right, text="Folder Tree Preview", style="CardSection.TLabel").grid(
            row=4, column=0, sticky="w", pady=(12, 0)
        )
        self.folder_preview = tk.Text(right, height=10, wrap="none")
        style_text_widget(self.folder_preview)
        self.folder_preview.grid(row=5, column=0, sticky="nsew", pady=(6, 0))
        folder_scroll = ttk.Scrollbar(right, orient="vertical", command=self.folder_preview.yview)
        folder_scroll.grid(row=5, column=1, sticky="ns", pady=(6, 0))
        self.folder_preview.configure(yscrollcommand=folder_scroll.set)

        ttk.Label(right, text="Log", style="CardSection.TLabel").grid(row=6, column=0, sticky="w", pady=(12, 0))
        self.log_text = tk.Text(right, height=12, wrap="word")
        style_text_widget(self.log_text)
        self.log_text.grid(row=7, column=0, sticky="nsew", pady=(6, 0))
        log_scroll = ttk.Scrollbar(right, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=7, column=1, sticky="ns", pady=(6, 0))
        self.log_text.configure(yscrollcommand=log_scroll.set)
        right.rowconfigure(7, weight=2)

    def _bind_events(self) -> None:
        self.source_var.trace_add("write", lambda *_: self._update_button_states())
        self.destination_var.trace_add("write", lambda *_: self._update_button_states())

    def _browse_source(self) -> None:
        selected = filedialog.askdirectory(title="Select source folder")
        if selected:
            self.source_var.set(selected)

    def _browse_destination(self) -> None:
        selected = filedialog.askdirectory(title="Select backup destination")
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
        visible_types = set(self._visible_file_types())
        for index, file_type in enumerate(FILE_TYPE_ORDER):
            checkbutton = self.type_checkbuttons[file_type]
            if file_type in visible_types:
                row = index // 3
                column = index % 3
                checkbutton.grid(row=row, column=column, sticky="w", padx=(0, 12), pady=(2, 0))
            else:
                checkbutton.grid_remove()
        if hasattr(self, "analyze_button"):
            self._update_button_states()

    def _selected_verify_mode(self) -> str:
        return VERIFY_LABEL_TO_MODE.get(self.verify_var.get(), "size")

    def _selected_duplicate_policy(self) -> str:
        return DUPLICATE_LABEL_TO_POLICY.get(self.duplicate_var.get(), "rename")

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
        source = Path(self.source_var.get())
        destination = Path(self.destination_var.get())
        if not source.is_dir():
            messagebox.showerror("Invalid Source", "Select a valid source folder.")
            return
        if destination.exists() and not destination.is_dir():
            messagebox.showerror("Invalid Destination", "Backup destination must be a folder.")
            return
        if not destination.exists() and not destination.parent.exists():
            messagebox.showerror("Invalid Destination", "Select a destination whose parent folder already exists.")
            return
        selected_types = self._selected_types()
        if not selected_types:
            messagebox.showwarning("No File Types", "Select at least one file type to scan.")
            return

        self._save_settings()
        self.current_summary = None
        self.pending_analysis = {
            "source_dir": source,
            "backup_root": destination,
            "enabled_types": selected_types,
        }
        self._set_busy(True, "Analyzing files...")
        self._run_worker(self._analyze_worker)

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

    def _preview_tree(self) -> None:
        if not self.current_summary:
            messagebox.showinfo("Preview", "Run Analyze Files first.")
            return
        self.folder_preview.focus_set()
        self.status_var.set("Folder preview refreshed.")

    def _start_backup(self) -> None:
        if not self.current_summary:
            messagebox.showinfo("Backup", "Run Analyze Files first.")
            return

        total = len(self.current_summary.items)
        destination = self.destination_var.get()
        confirmed = messagebox.askyesno(
            "Start Backup",
            f"{total} files will be processed.\n\nDestination:\n{destination}\n\nContinue?",
        )
        if not confirmed:
            return

        self._save_settings()
        self.pending_backup = {
            "items": list(self.current_summary.items),
            "duplicate_policy": self._selected_duplicate_policy(),
            "verify_mode": self._selected_verify_mode(),
            "dry_run": self.dry_run_var.get(),
        }
        self._set_busy(True, "Starting backup...")
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
        self.ui_queue.put(("backup_done", result))

    def _cancel_task(self) -> None:
        if self.is_busy:
            self.cancel_event.set()
            self.status_var.set("Cancel requested. Waiting for current file to finish...")

    def _open_in_image_manager(self) -> None:
        destination = self.destination_var.get().strip()
        if not destination or not Path(destination).is_dir():
            messagebox.showerror("Missing Folder", "Backup destination does not exist.")
            return
        launched = launch_app("image_manager", ["--open", "--source", destination])
        if not launched:
            messagebox.showerror(
                "Handoff",
                "Could not find NDEX Image Manager. Build or install it first.",
            )

    def _open_job_results(self) -> None:
        """Show what recent backups copied, skipped, or failed on."""
        from ndex_common.report_dialog import open_job_reports

        open_job_reports(self, title=NDEX_ONE_TITLE, apps=("ndex_one",))

    def _open_backup_folder(self) -> None:
        destination = Path(self.destination_var.get())
        if destination.exists():
            os.startfile(destination)  # type: ignore[attr-defined]
        else:
            messagebox.showerror("Missing Folder", "Backup destination does not exist.")

    def _run_worker(self, target) -> None:
        self.cancel_event.clear()
        self.worker_thread = threading.Thread(target=lambda: self._worker_wrapper(target), daemon=True)
        self.worker_thread.start()

    def _worker_wrapper(self, target) -> None:
        try:
            target()
        except Exception as exc:  # pragma: no cover - UI/runtime specific
            self.ui_queue.put(("error", str(exc)))

    def _queue_log(self, line: str) -> None:
        self.ui_queue.put(("log", line))

    def _queue_progress(self, stage: str, current: int, total: int, name: str) -> None:
        self.ui_queue.put(("progress", stage, current, total, name))

    def _process_ui_queue(self) -> None:
        while True:
            try:
                item = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            kind = item[0]
            if kind == "log":
                self.log_text.insert("end", item[1] + "\n")
                self.log_text.see("end")
            elif kind == "progress":
                _, stage, current, total, name = item
                progress = 0 if total == 0 else (current / total) * 100
                self.progress_var.set(progress)
                self.status_var.set(
                    f"{stage.title()} {current}/{total}: {name}"
                )
            elif kind == "analysis_done":
                self.current_summary = item[1]
                self._render_summary()
                self._set_busy(False, "Analysis completed.")
            elif kind == "backup_done":
                result = item[1]
                if result.cancelled:
                    status = "Backup cancelled."
                elif result.dry_run:
                    status = f"Dry run completed. Planned copies: {result.copied}"
                else:
                    status = (
                        f"Backup completed. Copied: {result.copied}, "
                        f"Verified: {result.verified}, "
                        f"Verify failed: {result.verification_failed}, "
                        f"Skipped: {result.skipped}, "
                        f"Errors: {result.errors}"
                    )
                    self._record_backup_session(result)
                self._render_backup_result(result)
                self._set_busy(False, status)
                if not result.dry_run and (result.verification_failed or result.errors):
                    messagebox.showwarning(
                        "Backup Warnings",
                        f"{result.verification_failed} file(s) failed verification and "
                        f"{result.errors} total error(s) occurred.\n\n"
                        "Failed files were NOT written to the backup destination — "
                        "existing backups are untouched. Check the log for details, "
                        "then run the backup again to retry failed files.",
                    )
            elif kind == "error":
                self._set_busy(False, item[1])
                messagebox.showerror("Error", item[1])

        self.after(100, self._process_ui_queue)

    def _render_summary(self) -> None:
        summary = self.current_summary
        total = sum(summary.counts.values())
        if summary.date_range[0] and summary.date_range[1]:
            date_range = (
                f"{summary.date_range[0]:%Y-%m-%d} ~ "
                f"{summary.date_range[1]:%Y-%m-%d}"
            )
        else:
            date_range = "No supported files found"

        summary_text = (
            f"Source: {summary.source_dir}\n"
            f"Destination: {summary.backup_root}\n"
            f"Total: {total}\n"
            f"Files: {self._format_type_counts(summary.counts)}\n"
            f"Date Range: {date_range}\n"
            f"Log File: {self.logger.log_path}"
        )
        self._summary_text = summary_text
        self.summary_var.set(summary_text)

        for row_id in self.preview_treeview.get_children():
            self.preview_treeview.delete(row_id)
        for row in summary.preview_rows:
            self.preview_treeview.insert(
                "",
                "end",
                values=(
                    row.date_label,
                    row.folder_rel_path.as_posix(),
                    self._format_type_counts(row.type_counts),
                    row.status,
                ),
            )

        self.folder_preview.delete("1.0", "end")
        self.folder_preview.insert("1.0", "\n".join(summary.folder_tree_lines))
        self.folder_preview.see("1.0")

    def _format_type_counts(self, counts: dict[str, int]) -> str:
        parts = []
        definitions = get_file_type_definitions()
        for file_type in FILE_TYPE_ORDER:
            count = counts.get(file_type, 0)
            if count:
                label = "JPG" if file_type == "jpg" else definitions[file_type]["label"].split(" ")[-1]
                parts.append(f"{label}: {count}")
        return " / ".join(parts) if parts else "None"

    def _record_backup_session(self, result) -> None:
        from ndex_common.workflow import record_backup

        record_backup(self.source_var.get().strip(), self.destination_var.get().strip(), result)

    def _render_backup_result(self, result) -> None:
        header = "Dry Run Result" if result.dry_run else "Backup Result"
        lines = [
            f"{header}: {result.copied} of {result.total} copied",
            f"  Verified: {result.verified} / Verify failed: {result.verification_failed}",
            f"  Skipped: {result.skipped} / Overwritten: {result.overwritten} / Errors: {result.errors}",
        ]
        if result.cancelled:
            lines.append("  Cancelled by user before completion.")
        self.summary_var.set(self._summary_text + "\n\n" + "\n".join(lines))

    def _set_busy(self, busy: bool, status: str) -> None:
        self.is_busy = busy
        self.status_var.set(status)
        if not busy:
            self.progress_var.set(0.0)
        self._update_button_states()

    def _update_button_states(self) -> None:
        has_paths = bool(self.source_var.get().strip()) and bool(self.destination_var.get().strip())
        has_analysis = self.current_summary is not None

        self.analyze_button.config(state="disabled" if self.is_busy or not has_paths else "normal")
        self.preview_button.config(state="disabled" if self.is_busy or not has_analysis else "normal")
        self.backup_button.config(state="disabled" if self.is_busy or not has_analysis else "normal")
        self.cancel_button.config(state="normal" if self.is_busy else "disabled")
        destination_ready = (
            "disabled" if self.is_busy or not self.destination_var.get().strip() else "normal"
        )
        self.open_button.config(state=destination_ready)
        self.handoff_button.config(state=destination_ready)


def run_app(
    initial_source: Path | None = None,
    initial_destination: Path | None = None,
    preload_only: bool = False,
) -> None:
    app = DSBApp(
        initial_source=initial_source,
        initial_destination=initial_destination,
        preload_only=preload_only,
    )
    app.mainloop()
