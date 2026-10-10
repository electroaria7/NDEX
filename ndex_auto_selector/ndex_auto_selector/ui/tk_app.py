from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.branding import NDEX_AUTO_SELECTOR_TITLE

from ndex_common.settings import get_section, update_section
from ndex_common.theme import (
    apply_tk_theme,
    apply_window_icon,
    build_app_header,
    style_text_widget,
)

from ..core.models import AnalysisSummary, CopyResult, SelectionMatch
from ..services.selector import AnalysisCancelled, AutoSelectorService, load_handoff, shared_camera_id

SETTINGS_SECTION = "auto_selector"

STATUS_LABELS = {
    "matched": "✔ Matched",
    "ambiguous": "⚠ Multiple RAW found",
    "missing": "✖ No RAW found",
    "chosen": "✔ Chosen",
}

# Policy key (stored in settings and passed to the service) -> label shown to the user.
DUPLICATE_LABELS = {
    "rename": "Keep both (add _001)",
    "skip": "Skip existing",
    "overwrite": "Replace existing (cannot be undone)",
}
PLACEHOLDER_TEXT = "Choose folders, then press Analyze Matches."


# --- Wording helpers (pure, unit-tested) -------------------------------------


def relative_folder(raw_path: Path | None, raw_root: Path | None) -> str:
    """Folder of ``raw_path`` relative to the RAW folder; an em dash for the top level."""
    if raw_path is None:
        return ""
    folder = raw_path.parent
    if raw_root is not None:
        try:
            relative = folder.relative_to(raw_root)
        except ValueError:
            return str(folder)
        return str(relative) if str(relative) != "." else "—"
    return str(folder)


def banner_for_analysis(summary: AnalysisSummary) -> str:
    return (
        f"{summary.selected_count} picked · {summary.copyable_count} will copy · "
        f"{summary.ambiguous_count} need your choice · {summary.missing_count} RAW not found"
    )


def banner_for_copy(result: CopyResult) -> str:
    return (
        f"Copied {result.copied} · Skipped {result.skipped + result.ambiguous} · "
        f"Not found {result.missing} · Failed {result.errors}"
    )


def hint_for_match(match: SelectionMatch | None, recursive: bool = True) -> str:
    """The line under the tree that explains the selected row."""
    if match is None:
        return ""
    if match.status == "missing":
        advice = "Check the folder." if recursive else "Check the folder or turn on Include subfolders."
        return f"No RAW named {match.file_stem} in the RAW folder. {advice}"
    if match.status == "ambiguous":
        return "Several RAW files match this photo. Choose one with Choose RAW…"
    if match.raw_path is None:
        return ""
    if match.status == "chosen":
        return f"{match.raw_path} — chosen by you"
    if match.match_kind == "camera_id":
        camera = shared_camera_id(match.jpg_path.stem, match.raw_path.stem)
        kind = f"camera number {camera}" if camera else "camera number"
    else:
        kind = "exact name"
    return f"{match.raw_path} — {kind}"


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def candidate_rows(match: SelectionMatch, raw_root: Path | None) -> list[tuple[str, str, str, str]]:
    """(folder, file, size, modified) for each RAW that could belong to the photo."""
    rows = []
    for path in match.candidates:
        try:
            info = path.stat()
            size = format_size(info.st_size)
            modified = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            size = modified = "?"
        rows.append((relative_folder(path, raw_root), path.name, size, modified))
    return rows


def handoff_text(count: int, folder: str) -> str:
    noun = "photo" if count == 1 else "photos"
    return f"{count} {noun} picked in Image Manager (from {folder})"


def open_folder(folder: str | Path) -> None:
    folder = str(folder)
    try:
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 - opens the folder in Explorer
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except OSError as exc:
        messagebox.showerror("Error", f"Couldn't open the folder: {exc}")


# --- Dialogs -----------------------------------------------------------------


class ChooseRawDialog(tk.Toplevel):
    """Modal list of the RAW files that fit one photo. ``result`` is set on exit."""

    def __init__(self, parent: tk.Misc, match: SelectionMatch, raw_root: Path | None):
        super().__init__(parent)
        self.match = match
        # ("choose", Path) | ("skip", None) | None (cancelled)
        self.result: tuple[str, Path | None] | None = None
        self.title("Choose RAW")
        self.configure(bg="#FFFFFF")
        self.transient(parent)
        self.resizable(True, False)

        frame = ttk.Frame(self, padding=16, style="CardInner.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text=f"Several RAW files match {match.jpg_path.name}. Choose the one to copy.",
            style="Card.TLabel",
            wraplength=540,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        columns = ("folder", "file", "size", "modified")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=min(max(len(match.candidates), 3), 8))
        for column, text, width in (
            ("folder", "Folder", 190), ("file", "File", 130), ("size", "Size", 70), ("modified", "Modified", 120),
        ):
            self.tree.heading(column, text=text)
            self.tree.column(column, width=width, anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        for index, row in enumerate(candidate_rows(match, raw_root)):
            self.tree.insert("", tk.END, iid=str(index), values=row)
        current = match.candidates.index(match.raw_path) if match.raw_path in match.candidates else 0
        if match.candidates:
            self.tree.selection_set(str(current))
            self.tree.focus(str(current))

        buttons = ttk.Frame(frame, style="CardInner.TFrame")
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self.use_button = ttk.Button(buttons, text="Use Selected RAW", style="Accent.TButton", command=self._choose)
        self.use_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Skip this photo", command=self._skip).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT)

        self.tree.bind("<Double-1>", lambda _e: self._choose())
        self.tree.bind("<Return>", lambda _e: self._choose())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        self._center(parent)
        self.tree.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _center(self, parent: tk.Misc) -> None:
        try:
            x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_reqwidth()) // 2, 0)
            y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_reqheight()) // 3, 0)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _choose(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.result = ("choose", self.match.candidates[int(selection[0])])
        self.destroy()

    def _skip(self) -> None:
        self.result = ("skip", None)
        self.destroy()


class CopyDoneDialog(tk.Toplevel):
    """Non-blocking completion message with the two obvious next steps."""

    def __init__(self, parent: tk.Misc, result: CopyResult, work_folder: str, on_results):
        super().__init__(parent)
        problems = result.errors > 0
        self.title("Copy finished with problems" if problems else "Copy complete")
        self.configure(bg="#FFFFFF")
        self.transient(parent)
        self.resizable(False, False)
        frame = ttk.Frame(self, padding=16, style="CardInner.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=banner_for_copy(result), style="CardSection.TLabel").pack(anchor="w")
        notes = []
        if result.ambiguous:
            notes.append(f"{result.ambiguous} photo(s) have several RAW matches and were skipped. "
                         "Choose a RAW for them, then copy again.")
        if result.missing:
            notes.append(f"{result.missing} photo(s) have no RAW in the RAW folder.")
        if result.skipped:
            notes.append(f"{result.skipped} RAW file(s) were already in the work folder.")
        if result.errors:
            notes.append(f"{result.errors} file(s) failed. Open Job Results to retry them.")
        for note in notes:
            ttk.Label(frame, text=note, style="CardMuted.TLabel", wraplength=420, justify="left").pack(
                anchor="w", pady=(6, 0)
            )
        buttons = ttk.Frame(frame, style="CardInner.TFrame")
        buttons.pack(anchor="e", pady=(14, 0))
        open_button = ttk.Button(
            buttons, text="Open Work Folder", style="Accent.TButton",
            command=lambda: (open_folder(work_folder), self.destroy()),
        )
        open_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            buttons, text="Job Results…", command=lambda: (self.destroy(), on_results()),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side=tk.LEFT)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        try:
            x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_reqwidth()) // 2, 0)
            y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_reqheight()) // 3, 0)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        open_button.focus_set()


class AutoSelectorApp(tk.Tk):
    show_completion_dialog = True

    def __init__(
        self,
        initial_raw_source=None,
        initial_selected_jpg=None,
        initial_work_folder=None,
        retry_manifest: Path | None = None,
        initial_handoff: Path | None = None,
    ):
        super().__init__()
        self._initial_handoff = initial_handoff
        # Exactly the JPGs an Image Manager handoff picked; None = scan the folder.
        self.handoff_files: list[Path] | None = None
        self._handoff_display = ""
        self._initial_raw_source = initial_raw_source
        self._initial_selected_jpg = initial_selected_jpg
        self._initial_work_folder = initial_work_folder
        self.title(NDEX_AUTO_SELECTOR_TITLE)
        self.geometry("1080x720")
        self.minsize(940, 620)
        self.brand_images: list[tk.PhotoImage] = []
        apply_window_icon(self, self.brand_images)

        self.service = AutoSelectorService()
        self.ui_queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.summary: AnalysisSummary | None = None
        self.cancel_event = threading.Event()
        self._busy = False
        self._closing = False
        self._closed = False
        self._analysis_context = None
        self._input_widgets: list[tuple[ttk.Widget, str]] = []
        self._xmp_dependents: list[ttk.Widget] = []
        self._wrapped_labels: list[ttk.Label] = []
        self._label_indent: dict[ttk.Label, int] = {}
        self._completion_dialog: tk.Toplevel | None = None

        self.raw_source_var = tk.StringVar()
        self.selected_jpg_var = tk.StringVar()
        self.selected_display_var = tk.StringVar()
        self.work_folder_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=True)
        self.duplicate_var = tk.StringVar(value="rename")
        self.duplicate_label_var = tk.StringVar(value=DUPLICATE_LABELS["rename"])
        self.write_xmp_var = tk.BooleanVar(value=True)
        self.xmp_rating_var = tk.StringVar(value="5")
        self.rating_from_jpg_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Choose the RAW folder and the selected-JPGs folder.")
        self.banner_var = tk.StringVar(value="")
        self.hint_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0.0)

        apply_tk_theme(self)
        self._build_ui()
        self._bind_events()
        self._apply_initial_paths()
        self._apply_initial_handoff()
        self._update_buttons()
        self._sync_placeholder()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._queue_after_id = self.after(100, self._process_queue)
        if retry_manifest is not None:
            # A job handed over by the launcher. It opens here; the retry itself is
            # started by the user in this window, where the settings are visible.
            self.after(150, lambda: self.open_job_results(select=Path(retry_manifest)))

    def _apply_initial_paths(self) -> None:
        stored = get_section(SETTINGS_SECTION)
        if stored.get("last_raw_source"):
            self.raw_source_var.set(stored["last_raw_source"])
        if stored.get("last_selected_jpg"):
            self.selected_jpg_var.set(stored["last_selected_jpg"])
        if stored.get("last_work_folder"):
            self.work_folder_var.set(stored["last_work_folder"])
        if "write_xmp" in stored:
            self.write_xmp_var.set(bool(stored["write_xmp"]))
        if "xmp_rating" in stored:
            self.xmp_rating_var.set(str(stored["xmp_rating"]))
        if "rating_from_jpg" in stored:
            self.rating_from_jpg_var.set(bool(stored["rating_from_jpg"]))
        if "recursive" in stored:
            self.recursive_var.set(bool(stored["recursive"]))
        if stored.get("duplicate_policy") in DUPLICATE_LABELS:
            self.duplicate_var.set(stored["duplicate_policy"])

        if self._initial_raw_source:
            self.raw_source_var.set(str(self._initial_raw_source))
        if self._initial_selected_jpg:
            self.selected_jpg_var.set(str(self._initial_selected_jpg))
        if self._initial_work_folder:
            self.work_folder_var.set(str(self._initial_work_folder))
        if self._initial_selected_jpg and not self._initial_raw_source:
            self.status_var.set("Selected JPGs folder linked. Choose the RAW folder.")

    def _apply_initial_handoff(self) -> None:
        if self._initial_handoff is None:
            return
        try:
            source, files = load_handoff(Path(self._initial_handoff))
        except ValueError as exc:
            messagebox.showerror(NDEX_AUTO_SELECTOR_TITLE, str(exc))
            return
        if not files:
            messagebox.showinfo(NDEX_AUTO_SELECTOR_TITLE, "The handoff has no JPG files.")
            return
        display = str(source or files[0].parent)
        self._handoff_display = display
        self.handoff_files = files
        self.selected_jpg_var.set(display)
        self._refresh_handoff_ui()
        self.status_var.set(f"Image Manager handoff: {len(files)} photos picked.")

    # --- layout ---------------------------------------------------------------

    def _build_ui(self) -> None:
        header = build_app_header(
            self,
            title=NDEX_AUTO_SELECTOR_TITLE,
            tagline="Match selected JPGs to original RAW files",
            holder=self.brand_images,
        )
        header.pack(fill=tk.X)

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))
        left = ttk.Frame(body, padding=(14, 10), style="Card.TFrame")
        right = ttk.Frame(body, padding=(14, 10), style="Card.TFrame")
        body.add(left, weight=2)
        body.add(right, weight=3)
        self.left_panel = left

        left.columnconfigure(0, weight=1)
        self.raw_entry, _ = self._path_row(
            left, 0, "RAW folder (CR3, CR2, ARW, NEF…)", self.raw_source_var, self._browse_raw_source)
        self.selected_entry, self.selected_browse = self._path_row(
            left, 2, "Selected JPGs folder", self.selected_jpg_var, self._browse_selected_jpg)
        self.work_entry, _ = self._path_row(
            left, 4, "Work folder (RAW copies go here)", self.work_folder_var, self._browse_work_folder)
        # Handoff mode swaps the browse button for this one.
        self.use_folder_button = ttk.Button(
            left, text="Use a folder instead", command=self._leave_handoff)
        self.use_folder_button.grid(row=2, column=0, columnspan=3, sticky="e")
        self.use_folder_button.grid_remove()

        recursive_check = ttk.Checkbutton(
            left, text="Include subfolders", variable=self.recursive_var, style="Card.TCheckbutton"
        )
        recursive_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self._input_widgets.append((recursive_check, "normal"))

        ttk.Label(left, text="If a file already exists", style="Card.TLabel").grid(row=7, column=0, sticky="w")
        duplicate_combo = ttk.Combobox(
            left,
            textvariable=self.duplicate_label_var,
            values=list(DUPLICATE_LABELS.values()),
            state="readonly",
        )
        duplicate_combo.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(2, 2))
        self._input_widgets.append((duplicate_combo, "readonly"))
        self._muted_note(left, 9, "Identical files already in the work folder are always skipped.", pady=(0, 6))

        xmp_row = ttk.Frame(left, style="CardInner.TFrame")
        xmp_row.grid(row=10, column=0, columnspan=3, sticky="ew")
        xmp_check = ttk.Checkbutton(
            xmp_row,
            text="Write XMP sidecar for copied RAW",
            variable=self.write_xmp_var,
            style="Card.TCheckbutton",
        )
        xmp_check.pack(side=tk.LEFT)
        self._input_widgets.append((xmp_check, "normal"))

        rating_row = ttk.Frame(xmp_row, style="CardInner.TFrame")
        rating_row.pack(side=tk.RIGHT)
        ttk.Label(rating_row, text="Star rating", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        rating_combo = ttk.Combobox(
            rating_row,
            textvariable=self.xmp_rating_var,
            values=["0", "1", "2", "3", "4", "5"],
            state="readonly",
            width=4,
        )
        rating_combo.pack(side=tk.LEFT)
        self._input_widgets.append((rating_combo, "readonly"))

        jpg_rating_check = ttk.Checkbutton(
            left,
            text="Use each JPG's star rating (fallback: rating above)",
            variable=self.rating_from_jpg_var,
            style="Card.TCheckbutton",
        )
        jpg_rating_check.grid(row=12, column=0, columnspan=3, sticky="w", padx=(22, 0))
        self._input_widgets.append((jpg_rating_check, "normal"))
        self._xmp_dependents = [rating_combo, jpg_rating_check]
        self._muted_note(
            left, 13, "Writes rating, label 'NDEX Selected' and keyword next to each copied RAW.",
            padx=(22, 0), pady=(0, 6))

        ttk.Label(left, textvariable=self.status_var, style="CardMuted.TLabel", wraplength=330).grid(
            row=14, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self._wrapped_labels.append(left.grid_slaves(row=14, column=0)[0])
        progress_row = ttk.Frame(left, style="CardInner.TFrame")
        progress_row.grid(row=15, column=0, columnspan=3, sticky="ew", pady=(4, 6))
        progress_row.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress_row, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.cancel_button = ttk.Button(progress_row, text="Cancel", command=self.cancel_work, state="disabled")
        self.cancel_button.grid(row=0, column=1)

        buttons = ttk.Frame(left, style="CardInner.TFrame")
        buttons.grid(row=16, column=0, columnspan=3, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        self.analyze_button = ttk.Button(buttons, text="Analyze Matches", command=self.start_analysis)
        self.copy_button = ttk.Button(
            buttons, text="Copy RAW Files", style="Accent.TButton", command=self.start_copy
        )
        self.analyze_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.copy_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        right.rowconfigure(2, weight=3)
        right.rowconfigure(5, weight=2)
        right.columnconfigure(0, weight=1)
        title_row = ttk.Frame(right, style="CardInner.TFrame")
        title_row.grid(row=0, column=0, columnspan=2, sticky="ew")
        title_row.columnconfigure(0, weight=1)
        ttk.Label(title_row, text="Match results", style="CardSection.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(title_row, text="Job Results…", command=self.open_job_results).grid(row=0, column=1, sticky="e")
        ttk.Label(right, textvariable=self.banner_var, style="Card.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 4))

        columns = ("jpg", "raw", "location", "status")
        self.match_tree = ttk.Treeview(right, columns=columns, show="headings", height=8, selectmode="browse")
        self.match_tree.grid(row=2, column=0, sticky="nsew")
        for column, text, width, stretch in (
            ("jpg", "Selected JPG", 150, True),
            ("raw", "Matched RAW", 120, True),
            ("location", "RAW location", 100, True),
            ("status", "Status", 145, False),
        ):
            self.match_tree.heading(column, text=text)
            self.match_tree.column(column, width=width, minwidth=70, anchor="w", stretch=stretch)
        self.match_tree.tag_configure("missing", foreground="#B91C1C")
        self.match_tree.tag_configure("ambiguous", foreground="#B45309")
        match_scroll = ttk.Scrollbar(right, orient="vertical", command=self.match_tree.yview)
        match_scroll.grid(row=2, column=1, sticky="ns")
        self.match_tree.configure(yscrollcommand=match_scroll.set)
        self.placeholder_label = ttk.Label(
            self.match_tree, text=PLACEHOLDER_TEXT, style="CardMuted.TLabel", anchor="center")

        hint_row = ttk.Frame(right, style="CardInner.TFrame")
        hint_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 6))
        hint_row.columnconfigure(0, weight=1)
        self.hint_label = ttk.Label(
            hint_row, textvariable=self.hint_var, style="CardMuted.TLabel", wraplength=380, justify="left")
        self.hint_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._wrapped_labels.append(self.hint_label)
        self.choose_button = ttk.Button(hint_row, text="Choose RAW…", command=self.choose_raw, state="disabled")
        self.choose_button.grid(row=0, column=1, sticky="ne")

        ttk.Label(right, text="Log", style="CardSection.TLabel").grid(row=4, column=0, sticky="w")
        self.log_text = tk.Text(right, height=5, wrap="word")
        style_text_widget(self.log_text)
        self.log_text.grid(row=5, column=0, sticky="nsew", pady=(4, 0))
        log_scroll = ttk.Scrollbar(right, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=5, column=1, sticky="ns", pady=(4, 0))
        self.log_text.configure(yscrollcommand=log_scroll.set)

        left.bind("<Configure>", self._on_left_resize)
        right.bind("<Configure>", self._on_right_resize)

    def _muted_note(self, parent, row: int, text: str, padx=(0, 0), pady=(0, 0)) -> ttk.Label:
        label = ttk.Label(parent, text=text, style="CardMuted.TLabel", wraplength=330, justify="left")
        label.grid(row=row, column=0, columnspan=3, sticky="w", padx=padx, pady=pady)
        self._wrapped_labels.append(label)
        self._label_indent[label] = int(padx[0]) if isinstance(padx, tuple) else 0
        return label

    def _on_left_resize(self, event) -> None:
        for label in self._wrapped_labels:
            if label is not self.hint_label:
                label.configure(wraplength=max(event.width - 36 - self._label_indent.get(label, 0), 160))

    def _on_right_resize(self, event) -> None:
        self.hint_label.configure(wraplength=max(event.width - 170, 160))
        self._place_placeholder()

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(1, 4))
        browse = ttk.Button(parent, text="Browse…", command=command)
        browse.grid(row=row + 1, column=2, sticky="ew", padx=(8, 0), pady=(1, 4))
        self._input_widgets.extend(((entry, "normal"), (browse, "normal")))
        return entry, browse

    def _bind_events(self) -> None:
        for variable in (self.raw_source_var, self.selected_jpg_var, self.work_folder_var):
            variable.trace_add("write", lambda *_: self._update_buttons())
        # All inputs that change matching or RAW exclusions invalidate it.
        for variable in (self.raw_source_var, self.selected_jpg_var, self.work_folder_var, self.recursive_var):
            variable.trace_add("write", lambda *_: self._invalidate_analysis())
        # The combobox shows labels; the rest of the app speaks policy keys.
        self.duplicate_label_var.trace_add("write", lambda *_: self._duplicate_label_changed())
        self.duplicate_var.trace_add("write", lambda *_: self._duplicate_key_changed())
        self._duplicate_key_changed()
        self.write_xmp_var.trace_add("write", lambda *_: self._apply_input_states())
        self.match_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_match_select())
        self.match_tree.bind("<Double-1>", self._on_match_activate)
        self.match_tree.bind("<Return>", self._on_match_activate)

    def _duplicate_label_changed(self) -> None:
        label = self.duplicate_label_var.get()
        for key, text in DUPLICATE_LABELS.items():
            if text == label and self.duplicate_var.get() != key:
                self.duplicate_var.set(key)

    def _duplicate_key_changed(self) -> None:
        label = DUPLICATE_LABELS.get(self.duplicate_var.get())
        if label and self.duplicate_label_var.get() != label:
            self.duplicate_label_var.set(label)

    def _current_analysis_context(self) -> tuple:
        return (
            self.raw_source_var.get().strip(), self.selected_jpg_var.get().strip(),
            self.work_folder_var.get().strip(), self.recursive_var.get(),
            tuple(self.handoff_files) if self.handoff_files is not None else None,
        )

    def _invalidate_analysis(self) -> None:
        if self.handoff_files is not None and self.selected_jpg_var.get() != self._handoff_display:
            # The JPG folder changed from outside the form: leave handoff mode.
            self.handoff_files = None
            self._refresh_handoff_ui()
        if self.summary is None:
            return
        self.summary = None
        self._clear_matches()
        self._render_summary()
        self.status_var.set("Settings changed. Run Analyze Matches again.")
        self._update_buttons()

    # --- handoff ----------------------------------------------------------------

    def _refresh_handoff_ui(self) -> None:
        """Show the handoff as a persistent read-only value, or the normal folder field."""
        if self.handoff_files is not None:
            self.selected_display_var.set(handoff_text(len(self.handoff_files), self._handoff_display))
            self.selected_entry.configure(textvariable=self.selected_display_var)
            self.selected_browse.grid_remove()
            self.use_folder_button.grid()
            self._set_resting_state(self.selected_entry, "readonly")
            self.selected_entry.grid_configure(columnspan=3)
        else:
            self.selected_entry.configure(textvariable=self.selected_jpg_var)
            self.selected_entry.grid_configure(columnspan=2)
            self.use_folder_button.grid_remove()
            self.selected_browse.grid()
            self._set_resting_state(self.selected_entry, "normal")

    def _leave_handoff(self) -> None:
        if self.handoff_files is None or self._busy or self._closing:
            return
        self.handoff_files = None
        self._handoff_display = ""
        self._refresh_handoff_ui()
        self._invalidate_analysis()
        self.status_var.set("Using the Selected JPGs folder. Run Analyze Matches.")
        self._update_buttons()

    def _set_resting_state(self, widget, state: str) -> None:
        self._input_widgets = [(w, state if w is widget else s) for w, s in self._input_widgets]
        self._apply_input_states()

    # --- browse ------------------------------------------------------------------

    def _browse_raw_source(self) -> None:
        selected = filedialog.askdirectory(title="Choose the RAW folder")
        if selected:
            self.raw_source_var.set(selected)

    def _browse_selected_jpg(self) -> None:
        selected = filedialog.askdirectory(title="Choose the selected-JPGs folder")
        if selected:
            self.selected_jpg_var.set(selected)

    def _browse_work_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose the work folder")
        if selected:
            self.work_folder_var.set(selected)

    def open_job_results(self, select: Path | None = None) -> None:
        """Show what each copy job actually copied, skipped or failed."""
        from ndex_common.report_dialog import open_job_reports

        open_job_reports(
            self,
            title=NDEX_AUTO_SELECTOR_TITLE,
            apps=("auto_selector",),
            retry=self._retry_extract,
            select=select,
        )

    def _retry_extract(self, plan) -> None:
        """Copy again only the JPGs that failed, were missing or were skipped.

        The folders come from that job's manifest: the ones in this window may
        be different from the ones the job used.
        """
        if self._busy or self._closing:
            messagebox.showinfo(NDEX_AUTO_SELECTOR_TITLE, "Wait for the current job to finish, then try again.")
            return

        selected_jpg = plan.report.source
        work_folder = plan.report.destination
        # The RAW folder is in the manifest's folders. Older manifests don't
        # have it, so fall back to the value in this window.
        raw_source = str(plan.report.folders.get("raw_source") or "").strip()
        raw_source = raw_source or self.raw_source_var.get().strip()

        for label, folder in (("RAW", raw_source), ("selected JPGs", selected_jpg)):
            if not folder or not Path(folder).is_dir():
                messagebox.showerror(
                    "Folder not found", f"Folder not found — can't find this job's {label} folder: {folder}")
                return
        if not work_folder:
            messagebox.showerror("Folder not found", "This job has no work folder recorded.")
            return

        options = self._copy_options()
        if not self._confirm_replace(len(plan.paths), options):
            return
        # The original run decided which folders were searched. Using the
        # checkbox as it stands now could drop JPGs the job found.
        options["recursive"] = bool(plan.report.context.get("recursive", True))
        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set(f"Retrying {len(plan.paths)} unfinished files…")
        self._log(f"Retry started: {len(plan.paths)} files")
        job = {
            "selected_jpg": selected_jpg,
            "raw_source": raw_source,
            "work_folder": work_folder,
            "options": options,
            "plan": plan,
        }
        self.worker_thread = threading.Thread(target=self._retry_worker, args=(job,), daemon=False)
        self.worker_thread.start()

    def _retry_worker(self, job: dict) -> None:
        plan, options = job["plan"], job["options"]
        selected_jpg, raw_source, work_folder = job["selected_jpg"], job["raw_source"], job["work_folder"]
        try:
            # Analyze again: the user may have added a missing RAW or tidied up
            # duplicates since the job ran, which is the reason to retry.
            summary = self.service.analyze(
                Path(raw_source),
                Path(selected_jpg),
                recursive=options["recursive"],
                exclude=Path(work_folder),
                jpg_files=list(plan.paths),
                cancel_event=self.cancel_event,
            )
            matches, dropped = self.service.matches_for(summary.matches, list(plan.paths))
            result = self._copy(matches, Path(work_folder), options)
            # A JPG the analysis no longer lists would otherwise vanish from
            # the record. Count it as missing so the manifest says so.
            self.service.note_missing(result, dropped, "not in the selected JPG folder")
            self._record_copy_result(result, job)
            self.ui_queue.put(("copy_done", result, job))
        except AnalysisCancelled:
            result = CopyResult(total=len(plan.paths), errors=len(plan.paths), cancelled=True)
            result.items = [{"path": str(path), "status": "failed", "detail": "not run: cancelled"}
                            for path in plan.paths]
            self._record_copy_result(result, job)
            self.ui_queue.put(("copy_done", result, job))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def start_analysis(self) -> None:
        if self._busy or self._closing:
            return
        raw_source = self.raw_source_var.get().strip()
        selected_jpg = self.selected_jpg_var.get().strip()
        if not raw_source or not selected_jpg:
            messagebox.showwarning("Folders required", "Choose the RAW folder and the selected-JPGs folder.")
            return
        self._set_busy(True)
        self._analysis_context = self._current_analysis_context()
        self.summary = None
        self._render_summary()
        self.progress_var.set(0)
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start(15)
        self.status_var.set("Analyzing…")
        self._clear_matches()
        self._log("Analysis started")
        self.worker_thread = threading.Thread(
            target=self._analysis_worker,
            args=(
                Path(raw_source),
                Path(selected_jpg),
                self.recursive_var.get(),
                Path(self.work_folder_var.get().strip()) if self.work_folder_var.get().strip() else None,
                list(self.handoff_files) if self.handoff_files is not None else None,
            ),
            daemon=False,
        )
        self.worker_thread.start()

    def _analysis_worker(
        self,
        raw_source: Path,
        selected_jpg: Path,
        recursive: bool,
        exclude: Path | None = None,
        jpg_files: list[Path] | None = None,
    ) -> None:
        try:
            summary = self.service.analyze(
                raw_source, selected_jpg, recursive=recursive, exclude=exclude, jpg_files=jpg_files,
                cancel_event=self.cancel_event,
            )
            self.ui_queue.put(("analysis_done", summary))
        except AnalysisCancelled:
            self.ui_queue.put(("analysis_cancelled",))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def _copy_options(self) -> dict:
        """What a copy run needs from the form, read on the UI thread."""
        try:
            rating = int(self.xmp_rating_var.get())
        except (TypeError, ValueError):
            rating = 5
        return {
            "duplicate_policy": self.duplicate_var.get(),
            "recursive": self.recursive_var.get(),
            "write_xmp": self.write_xmp_var.get(),
            "xmp_rating": rating,
            "rating_from_jpg": self.rating_from_jpg_var.get(),
        }

    def _save_settings(self, job: dict) -> None:
        """Persist the form snapshot on the worker, without reading Tk variables."""
        options = job["options"]
        try:
            update_section(
                SETTINGS_SECTION,
                {
                    "last_raw_source": job["raw_source"],
                    "last_selected_jpg": job["selected_jpg"],
                    "last_work_folder": job["work_folder"],
                    "write_xmp": options["write_xmp"],
                    "xmp_rating": options["xmp_rating"],
                    "rating_from_jpg": options["rating_from_jpg"],
                    "duplicate_policy": options["duplicate_policy"],
                    "recursive": options["recursive"],
                },
            )
            from ndex_common.session import remember

            remember(
                "auto_selector",
                folders={
                    "selected_jpg": job["selected_jpg"],
                    "raw_source": job["raw_source"],
                    "work": job["work_folder"],
                },
            )
        except OSError:
            pass

    def _confirm_replace(self, count: int, options: dict, matches=None, work_folder: str = "") -> bool:
        """Replacing cannot be undone, so say how many files it may touch."""
        if options["duplicate_policy"] != "overwrite" or count <= 0:
            return True
        if matches is not None and work_folder:
            existing = sum(
                1 for match in matches
                if match.raw_path is not None and (Path(work_folder) / match.raw_path.name).exists()
            )
            if existing == 0:
                return True
            count = existing
        return messagebox.askyesno(
            NDEX_AUTO_SELECTOR_TITLE,
            f"Replace up to {count} existing RAW files in the work folder?\n\nThis cannot be undone.",
            default="no",
            icon="warning",
        )

    def start_copy(self) -> None:
        if self._busy or self._closing:
            return
        if self.summary is None:
            messagebox.showwarning("Analysis required", "Analysis required — run Analyze Matches first.")
            return
        if (
            Path(self.raw_source_var.get().strip()) != self.summary.raw_source_dir
            or Path(self.selected_jpg_var.get().strip()) != self.summary.selected_jpg_dir
            or self._analysis_context != self._current_analysis_context()
        ):
            self.summary = None
            self._update_buttons()
            messagebox.showwarning(NDEX_AUTO_SELECTOR_TITLE, "Settings changed. Run Analyze Matches again.")
            return
        work_folder = self.work_folder_var.get().strip()
        if not work_folder:
            messagebox.showwarning(
                "Work folder required", "Work folder required — choose a folder to copy the RAW files into.")
            return
        options = self._copy_options()
        copyable = [m for m in self.summary.matches if m.status in ("matched", "chosen")]
        if not self._confirm_replace(len(copyable), options, copyable, work_folder):
            return
        # Fixed now, not read when the job ends: the form can change while
        # the copy runs, and the manifest must say what the job used.
        job = {
            "selected_jpg": str(self.summary.selected_jpg_dir),
            "raw_source": str(self.summary.raw_source_dir),
            "work_folder": work_folder,
            "options": options,
            "matches": list(self.summary.matches),
            "plan": None,
        }
        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set("Copying RAW files…")
        self._log("Copy started")
        self.worker_thread = threading.Thread(target=self._copy_worker, args=(job,), daemon=False)
        self.worker_thread.start()

    def _copy_worker(self, job: dict) -> None:
        try:
            self._save_settings(job)
            result = self._copy(job["matches"], Path(job["work_folder"]), job["options"])
            self._record_copy_result(result, job)
            self.ui_queue.put(("copy_done", result, job))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    @staticmethod
    def _record_copy_result(result, job: dict) -> None:
        """Keep the UI responsive while workflow/settings locks are acquired."""
        from ndex_common.workflow import record_extract

        plan = job["plan"]
        try:
            manifest = record_extract(
                job["selected_jpg"], job["raw_source"], job["work_folder"], result,
                recursive=job["options"]["recursive"],
                context=plan.context() if plan is not None else None,
            )
            job["manifest"] = manifest
            if manifest is None:
                job["record_error"] = "Couldn't save the job record. Check the log for what was processed."
        except Exception as exc:
            job["record_error"] = f"Couldn't save the job record: {exc}"

    def _copy(self, matches, work_folder: Path, options: dict):
        return self.service.copy_matches(
            matches,
            work_folder,
            options["duplicate_policy"],
            write_xmp=options["write_xmp"],
            xmp_rating=options["xmp_rating"],
            rating_from_jpg=options["rating_from_jpg"],
            cancel_event=self.cancel_event,
            progress_callback=lambda current, total, name: self.ui_queue.put(
                ("progress", current, total, name)
            ),
        )

    def _process_queue(self) -> None:
        try:
            while True:
                try:
                    event = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._dispatch_event(event)
                except Exception:
                    self._report_handler_failure()
        finally:
            if not getattr(self, "_closed", False):
                self._queue_after_id = self.after(100, self._process_queue)

    def _dispatch_event(self, event) -> None:
        kind = event[0]
        if kind == "analysis_done":
            self._handle_analysis_done(event[1])
        elif kind == "analysis_cancelled":
            self.summary = None
            self._render_summary()
            self.status_var.set("Analysis cancelled.")
            self._log("Analysis cancelled")
            self._set_busy(False)
        elif kind == "copy_done":
            _, result, job = event
            self._handle_copy_done(result, job)
        elif kind == "progress":
            _, current, total, name = event
            self.progress_var.set((current / total) * 100 if total else 0)
            if not self.cancel_event.is_set():
                self.status_var.set(f"Copying {current} of {total}: {name}")
        elif kind == "error":
            self._handle_error(event[1])

    def _report_handler_failure(self) -> None:
        """A handler crashed: log it and unfreeze the UI instead of leaving it busy."""
        from ndex_common.crashlog import write_crash_log

        exc_type, exc, tb = sys.exc_info()
        write_crash_log("NDEX Auto Selector", exc_type, exc, tb)
        try:
            self.status_var.set("Job failed")
            self._log(f"Error: {exc}")
            self._closing = False
            self._set_busy(False)
            messagebox.showerror(NDEX_AUTO_SELECTOR_TITLE, str(exc))
        except Exception:
            pass

    def _handle_analysis_done(self, summary: AnalysisSummary) -> None:
        if self.cancel_event.is_set() or self._analysis_context != self._current_analysis_context():
            self.summary = None
            self._render_summary()
            self.status_var.set("Analysis cancelled or settings changed. Run Analyze Matches again.")
            self._set_busy(False)
            return
        self.summary = summary
        self._render_summary()
        self._render_matches()
        self.progress_var.set(100)
        self.status_var.set("Analysis complete")
        self._log(
            f"Analysis complete: {summary.selected_count} JPGs, {summary.matched_count} matched, "
            f"{summary.ambiguous_count} ambiguous, {summary.missing_count} no RAW"
        )
        self._set_busy(False)

    def _handle_copy_done(self, result, job: dict) -> None:
        """``job`` is what the run was started with; ``job["plan"]`` marks a retry."""
        completed = result.total - sum(item.get("detail") == "not run: cancelled" for item in result.items)
        self.progress_var.set(completed / result.total * 100 if result.total else 0)
        self.status_var.set("Copy cancelled. Unprocessed files can be retried from Job Results."
                            if result.cancelled else "Copy complete")
        self.banner_var.set(banner_for_copy(result))
        self._log(
            f"Copy finished: copied={result.copied}, xmp={result.xmp_written}, skipped={result.skipped}, "
            f"overwritten={result.overwritten}, ambiguous={result.ambiguous}, "
            f"not found={result.missing}, errors={result.errors}"
        )
        for message in result.messages[:80]:
            self._log(message)
        if len(result.messages) > 80:
            self._log(f"... {len(result.messages) - 80} more messages not shown")
        if job.get("record_error"):
            # A failed report must remain visible even if Close was requested
            # while the worker was saving it.
            self._closing = False
            self._log(job["record_error"])
            self.status_var.set(job["record_error"])
        was_closing = self._closing
        self._set_busy(False)
        if job.get("record_error"):
            messagebox.showwarning(NDEX_AUTO_SELECTOR_TITLE, job["record_error"])
        elif self.show_completion_dialog and not result.cancelled and not was_closing and not self._closed:
            self._show_completion(result, job)

    def _show_completion(self, result: CopyResult, job: dict) -> None:
        if self._completion_dialog is not None:
            try:
                self._completion_dialog.destroy()
            except tk.TclError:
                pass
        manifest = job.get("manifest")
        self._completion_dialog = CopyDoneDialog(
            self, result, job["work_folder"], lambda: self.open_job_results(select=manifest)
        )

    def _handle_error(self, message: str) -> None:
        self.status_var.set("Job failed")
        self._log(f"Error: {message}")
        self._closing = False
        self._set_busy(False)
        messagebox.showerror("Error", message)

    # --- results view -------------------------------------------------------------

    def _render_summary(self) -> None:
        """The one-line banner above the tree."""
        self.banner_var.set("" if self.summary is None else banner_for_analysis(self.summary))
        if self.summary is None:
            self.hint_var.set("")
            self._update_choose_button()

    def _render_matches(self) -> None:
        self._clear_matches()
        if self.summary is None:
            return
        for index, match in enumerate(self.summary.matches):
            self.match_tree.insert("", tk.END, iid=str(index), values=self._row_values(match),
                                   tags=(match.status,))
        self._sync_placeholder()

    def _row_values(self, match: SelectionMatch) -> tuple[str, str, str, str]:
        root = self.summary.raw_source_dir if self.summary is not None else None
        if match.status == "ambiguous":
            raw_cell, location = f"({len(match.candidates)} candidates)", ""
        else:
            raw_cell = match.raw_path.name if match.raw_path else ""
            location = relative_folder(match.raw_path, root)
        return (match.jpg_path.name, raw_cell, location, STATUS_LABELS.get(match.status, match.status))

    def _clear_matches(self) -> None:
        for item_id in self.match_tree.get_children():
            self.match_tree.delete(item_id)
        self.hint_var.set("")
        self._update_choose_button()
        self._sync_placeholder()

    def _sync_placeholder(self) -> None:
        if self.match_tree.get_children():
            self.placeholder_label.place_forget()
            return
        if self.summary is not None:
            self.placeholder_label.configure(text="No selected JPGs were found.")
        else:
            self.placeholder_label.configure(text=PLACEHOLDER_TEXT)
        self._place_placeholder()

    def _place_placeholder(self) -> None:
        if not self.match_tree.get_children():
            self.placeholder_label.place(relx=0.5, rely=0.45, anchor="center")

    def _selected_match(self) -> tuple[int, SelectionMatch] | None:
        if self.summary is None:
            return None
        selection = self.match_tree.selection()
        if not selection:
            return None
        try:
            index = int(selection[0])
            return index, self.summary.matches[index]
        except (ValueError, IndexError):
            return None

    def _on_match_select(self) -> None:
        picked = self._selected_match()
        self.hint_var.set(hint_for_match(picked[1] if picked else None, self.recursive_var.get()))
        self._update_choose_button()

    def _update_choose_button(self) -> None:
        picked = self._selected_match()
        can_choose = (
            picked is not None and bool(picked[1].candidates)
            and not self._busy and not self._closing
        )
        self.choose_button.configure(state="normal" if can_choose else "disabled")

    def _on_match_activate(self, _event=None):
        self.choose_raw()
        return "break"

    def choose_raw(self) -> None:
        picked = self._selected_match()
        if picked is None or not picked[1].candidates or self._busy or self._closing:
            return
        index, match = picked
        result = self._run_choose_dialog(match)
        if result is not None:
            self._apply_choice(index, result)

    def _run_choose_dialog(self, match: SelectionMatch):
        dialog = ChooseRawDialog(self, match, self.summary.raw_source_dir if self.summary else None)
        self.wait_window(dialog)
        return dialog.result

    def _apply_choice(self, index: int, result: tuple[str, Path | None]) -> None:
        """Record the user's pick (or skip) on the match and refresh the row."""
        if self.summary is None:
            return
        match = self.summary.matches[index]
        action, path = result
        if action == "choose" and path is not None:
            match.raw_path, match.status, match.match_kind = path, "chosen", ""
        else:
            match.raw_path, match.status, match.match_kind = None, "ambiguous", ""
        iid = str(index)
        self.match_tree.item(iid, values=self._row_values(match), tags=(match.status,))
        self._render_summary()
        self.match_tree.selection_set(iid)
        self._on_match_select()
        label = f"chose {path.name}" if action == "choose" and path else "skipped"
        self._log(f"{match.jpg_path.name}: {label}")
        self._update_buttons()

    def _log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    # --- busy / closing -----------------------------------------------------------

    def _input_state(self, widget, resting: str) -> str:
        if self._busy or self._closing:
            return "disabled"
        if widget in self._xmp_dependents and not self.write_xmp_var.get():
            return "disabled"
        return resting

    def _apply_input_states(self) -> None:
        for widget, state in self._input_widgets:
            widget.configure(state=self._input_state(widget, state))
        self.use_folder_button.configure(state="disabled" if self._busy or self._closing else "normal")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self.cancel_event.clear()
        else:
            self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self._apply_input_states()
        self.cancel_button.configure(state="normal" if busy and not self._closing else "disabled")
        self._update_buttons()
        if not busy and self._closing:
            self._finish_close()

    def cancel_work(self) -> None:
        if not self._busy:
            return
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Cancelling after the current file finishes copying and verifying…")

    def _on_close(self) -> None:
        if self._closing or self._closed:
            return
        self._closing = True
        if self._busy:
            self.cancel_work()
            self.status_var.set("Closing after the current file; saving the job record…")
            self._update_buttons()
        else:
            self._finish_close()

    def _finish_close(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            self.after(50, self._finish_close)
            return
        self._closed = True
        self.after_cancel(self._queue_after_id)
        self.destroy()

    def _update_buttons(self) -> None:
        available = not self._busy and not self._closing
        self.analyze_button.configure(state=tk.NORMAL if available and self._can_analyze() else tk.DISABLED)
        self.copy_button.configure(state=tk.NORMAL if available and self._can_copy() else tk.DISABLED)
        self._update_choose_button()

    def _can_analyze(self) -> bool:
        return bool(self.raw_source_var.get().strip() and self.selected_jpg_var.get().strip())

    def _can_copy(self) -> bool:
        return self.summary is not None and bool(self.work_folder_var.get().strip())


def run_app(
    initial_raw_source=None,
    initial_selected_jpg=None,
    initial_work_folder=None,
    retry_manifest: Path | None = None,
    initial_handoff: Path | None = None,
) -> None:
    app = AutoSelectorApp(
        initial_raw_source=initial_raw_source,
        initial_selected_jpg=initial_selected_jpg,
        initial_work_folder=initial_work_folder,
        retry_manifest=retry_manifest,
        initial_handoff=initial_handoff,
    )
    app.mainloop()
