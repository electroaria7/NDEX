"""Shared Tk window that shows what recent NDEX jobs did.

NDEX One, Image Manager, Auto Selector, and the Launcher all open this same
window; they differ only in which apps they ask for. NDEX Frame is Qt and has
its own dialog.

The window reads manifests; it never edits one. It can start a retry, but
only by handing the failed files back to the app that ran the job — the
window itself copies nothing.
"""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Iterable, Sequence

from ndex_common.report import JobReport, including, index_of, recent_reports
from ndex_common.retry import RetryPlan, plan_retry, retryable, supports_retry
from ndex_common.theme import (
    BODY_PAD,
    DANGER,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    apply_tk_theme,
    apply_window_icon,
    style_text_widget,
)

_HISTORY_LIMIT = 30


def open_job_reports(
    parent: tk.Misc,
    *,
    title: str,
    apps: Sequence[str] | None = None,
    reports: Sequence[JobReport] | None = None,
    retry: Callable[[RetryPlan], None] | None = None,
    open_in_app: Callable[[JobReport], None] | None = None,
    select: Path | None = None,
) -> tk.Toplevel | None:
    """Open the results window, or explain that there is nothing to show.

    ``reports`` is for tests and for callers that already loaded them; normally
    the window reads the manifest folder itself. ``retry`` is what runs a job's
    failed files again. ``open_in_app`` is the Launcher's substitute: it cannot
    run anything, so it hands the job to the app that can. ``select`` picks a
    job on open, and is read in even when it has aged out of the recent list.
    """
    found = list(reports) if reports is not None else recent_reports(apps=apps, limit=_HISTORY_LIMIT)
    found = including(found, select, apps=apps)
    if not found:
        messagebox.showinfo(
            title,
            "No job results yet.\n\n"
            "Backups, extracts, exports, and picks sent to Frame are recorded "
            "once they finish, and show up here.",
            parent=parent,
        )
        return None
    return JobReportWindow(
        parent, title=title, reports=found, retry=retry, open_in_app=open_in_app, select=select
    )


class JobReportWindow(tk.Toplevel):
    """A job list on the left, the selected job's items on the right."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        reports: Sequence[JobReport],
        retry: Callable[[RetryPlan], None] | None = None,
        open_in_app: Callable[[JobReport], None] | None = None,
        select: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(f"{title} - Job Results")
        self.geometry("980x600")
        self.minsize(760, 460)
        self.brand_images: list[tk.PhotoImage] = []
        apply_tk_theme(self)
        if isinstance(parent, tk.Tk):
            self.transient(parent)
        try:
            apply_window_icon(self, self.brand_images)  # type: ignore[arg-type]
        except tk.TclError:
            pass

        self.reports = list(reports)
        self.current: JobReport | None = None
        self.retry = retry
        self.open_in_app = open_in_app

        body = ttk.Frame(self, padding=BODY_PAD)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=0, minsize=320)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_job_list(body)
        self._build_detail(body)

        first = str(index_of(self.reports, select))
        self.job_list.selection_set(first)
        self.job_list.focus(first)
        self.job_list.see(first)
        self._show_selected()

    def destroy(self) -> None:
        # Release the icon images while Tk is still up. Left to the garbage
        # collector they are finalized after teardown, and Tcl aborts.
        self.brand_images.clear()
        super().destroy()

    # ------------------------------------------------------------------ build

    def _build_job_list(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, padding=SPACE_MD, style="Card.TFrame")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_MD))
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text="Recent jobs", style="CardSection.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, SPACE_SM)
        )

        self.job_list = ttk.Treeview(card, columns=("app", "job"), show="headings", selectmode="browse")
        self.job_list.heading("app", text="App")
        self.job_list.heading("job", text="Job")
        self.job_list.column("app", width=110, stretch=False)
        self.job_list.column("job", width=380)
        self.job_list.grid(row=1, column=0, sticky="nsew")
        self.job_list.tag_configure("problem", foreground=DANGER)

        scroll = ttk.Scrollbar(card, orient=tk.VERTICAL, command=self.job_list.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.job_list.configure(yscrollcommand=scroll.set)

        for index, report in enumerate(self.reports):
            self.job_list.insert(
                "",
                tk.END,
                iid=str(index),
                values=(report.app_label, report.headline),
                tags=("problem",) if report.failed_count else (),
            )
        self.job_list.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())

    def _build_detail(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, padding=SPACE_MD, style="Card.TFrame")
        card.grid(row=0, column=1, sticky="nsew")
        card.rowconfigure(3, weight=1)
        card.columnconfigure(0, weight=1)

        self.detail_title = ttk.Label(card, text="", style="CardTitle.TLabel")
        self.detail_title.grid(row=0, column=0, sticky="w")

        self.detail_counts = ttk.Label(card, text="", style="CardMuted.TLabel", wraplength=560, justify="left")
        self.detail_counts.grid(row=1, column=0, sticky="w", pady=(SPACE_SM, 0))

        self.detail_folders = ttk.Label(card, text="", style="CardFaint.TLabel", wraplength=560, justify="left")
        self.detail_folders.grid(row=2, column=0, sticky="w", pady=(SPACE_SM, SPACE_MD))

        self.item_text = tk.Text(card, wrap="none", height=16)
        style_text_widget(self.item_text)
        self.item_text.grid(row=3, column=0, sticky="nsew")
        item_scroll = ttk.Scrollbar(card, orient=tk.VERTICAL, command=self.item_text.yview)
        item_scroll.grid(row=3, column=1, sticky="ns")
        self.item_text.configure(yscrollcommand=item_scroll.set, state=tk.DISABLED)

        actions = ttk.Frame(card, style="CardInner.TFrame")
        actions.grid(row=4, column=0, columnspan=2, sticky="w", pady=(SPACE_MD, 0))

        self.retry_button = ttk.Button(
            actions, text="Retry Failed", style="Accent.TButton", command=self._retry_failed
        )
        if self.retry is not None:
            self.retry_button.pack(side=tk.LEFT, padx=(0, SPACE_SM))

        # The Launcher cannot run a job. Its button opens the app that can,
        # at this very job, and that app's own Retry button takes it from there.
        self.open_app_button = ttk.Button(actions, text="Retry in app...", command=self._open_in_app)
        if self.retry is None and self.open_in_app is not None:
            self.open_app_button.pack(side=tk.LEFT, padx=(0, SPACE_SM))

        self.copy_button = ttk.Button(actions, text="Copy Problem Paths", command=self._copy_problems)
        self.copy_button.pack(side=tk.LEFT)
        self.source_button = ttk.Button(actions, text="Open Source Folder", command=self._open_source)
        self.source_button.pack(side=tk.LEFT, padx=(SPACE_SM, 0))
        self.destination_button = ttk.Button(
            actions, text="Open Destination Folder", command=self._open_destination
        )
        self.destination_button.pack(side=tk.LEFT, padx=(SPACE_SM, 0))
        ttk.Button(actions, text="Open Manifest Folder", command=self._open_manifest_folder).pack(
            side=tk.LEFT, padx=(SPACE_SM, 0)
        )
        ttk.Button(actions, text="Close", command=self.destroy).pack(side=tk.LEFT, padx=(SPACE_LG, 0))

    # ----------------------------------------------------------------- render

    def _show_selected(self) -> None:
        selection = self.job_list.selection()
        if not selection:
            return
        report = self.reports[int(selection[0])]
        self.current = report

        self.detail_title.configure(text=f"{report.app_label} - {report.type_label}")
        counts = f"{report.display_time}   {report.count_summary}"
        if report.cancelled:
            counts = f"{counts}   (cancelled)"
        self.detail_counts.configure(text=counts)
        self.detail_folders.configure(text=_folder_lines(report))

        self.item_text.configure(state=tk.NORMAL)
        self.item_text.delete("1.0", tk.END)
        self.item_text.insert("1.0", _item_listing(report))
        self.item_text.configure(state=tk.DISABLED)

        problems = report.problem_paths()
        # Whether those files are still on disk is checked when the button is
        # pressed, not here: a manifest can point at a card since unplugged.
        self.retry_button.state(
            ["!disabled"] if self.retry is not None and retryable(report) else ["disabled"]
        )
        self.open_app_button.configure(text=f"Retry in {report.app_label}...")
        self.open_app_button.state(
            ["!disabled"] if self.open_in_app is not None and retryable(report) else ["disabled"]
        )
        self.copy_button.state(["!disabled"] if problems else ["disabled"])
        self.source_button.state(["!disabled"] if _is_dir(report.source) else ["disabled"])
        self.destination_button.state(["!disabled"] if _is_dir(report.destination) else ["disabled"])

    # ---------------------------------------------------------------- actions

    def _retry_failed(self) -> None:
        """Hand the still-present failed files back to the app that ran them."""
        report, run = self.current, self.retry
        if report is None or run is None or not retryable(report):
            return
        plan = plan_retry(report)
        if not plan.ready:
            messagebox.showinfo(self.title(), plan.summary, parent=self)
            return
        if not messagebox.askyesno(self.title(), plan.question(), parent=self):
            return
        # Close first: the app takes over the screen from here, and this list
        # is about to be one job out of date.
        self.destroy()
        run(plan)

    def _open_in_app(self) -> None:
        """Hand this job to the app that ran it; that app offers the retry."""
        report, run = self.current, self.open_in_app
        if report is None or run is None or not retryable(report):
            return
        self.destroy()
        run(report)

    def _copy_problems(self) -> None:
        if self.current is None:
            return
        paths = self.current.problem_paths()
        if not paths:
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(paths))
        messagebox.showinfo(
            self.title(),
            f"Copied {len(paths)} path(s) to the clipboard.\n\n"
            + _where_to_retry(self.current, self.retry is not None),
            parent=self,
        )

    def _open_source(self) -> None:
        if self.current is not None:
            self._reveal(Path(self.current.source))

    def _open_destination(self) -> None:
        if self.current is not None:
            self._reveal(Path(self.current.destination))

    def _open_manifest_folder(self) -> None:
        if self.current is not None:
            self._reveal(self.current.manifest_path.parent)

    def _reveal(self, folder: Path) -> None:
        try:
            reveal_folder(folder)
        except OSError as exc:
            messagebox.showerror(self.title(), f"Could not open the folder:\n{exc}", parent=self)


def reveal_folder(folder: Path) -> bool:
    """Open a folder in the desktop file manager. False when it is missing."""
    if not folder.is_dir():
        return False
    if sys.platform == "win32":
        subprocess.Popen(["explorer", str(folder)], close_fds=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)], close_fds=True)
    else:
        subprocess.Popen(["xdg-open", str(folder)], close_fds=True)
    return True


def _where_to_retry(report: JobReport, here: bool) -> str:
    """Point at whoever can run these files again.

    The Launcher shows every app's jobs but runs none of them, so from there
    the answer is always another window.
    """
    if not supports_retry(report):
        return "Re-run the job with the same folders to retry them."
    if here:
        return "Retry Failed runs the ones that are still on disk."
    return f"Open {report.app_label} and use Job Results there to retry them."



def _folder_lines(report: JobReport) -> str:
    lines = []
    if report.source:
        lines.append(f"Source: {report.source}")
    if report.destination:
        lines.append(f"Destination: {report.destination}")
    lines.append(f"Manifest: {report.manifest_path.name}")
    return "\n".join(lines)


def _item_listing(report: JobReport) -> str:
    """Items grouped by status, problems first."""
    grouped = report.items_by_status()
    if not grouped:
        return "This job recorded no per-file items."

    blocks = []
    for status, items in grouped.items():
        block = [f"{status} ({len(items)})"]
        block.extend(f"    {line}" for line in _item_lines(items))
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


def _item_lines(items: Iterable) -> list[str]:
    lines = []
    for item in items:
        text = item.path or "(no path)"
        if item.detail:
            text = f"{text}  -  {item.detail}"
        lines.append(text)
    return lines


def _is_dir(value: str) -> bool:
    return bool(value) and Path(value).is_dir()


__all__ = ["JobReportWindow", "open_job_reports", "reveal_folder"]
