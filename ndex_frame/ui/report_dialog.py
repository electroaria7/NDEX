"""Qt window showing what recent NDEX Frame jobs did.

The Tk apps share ``ndex_common.report_dialog``; Frame is PySide6, so it reads
the same manifests through ``ndex_common.report`` and renders them here.

It reads manifests and never edits one. It can start a retry, but only by
handing the failed files back to the window that ran the export.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ndex_common.report import JobReport, read_report, recent_reports
from ndex_common.retry import RetryPlan, plan_retry, retryable

HISTORY_LIMIT = 30


class FrameJobReportDialog(QDialog):
    """Recent Frame jobs on the left, the selected job's items below."""

    def __init__(
        self,
        reports: Sequence[JobReport],
        parent: QWidget | None = None,
        retry: Callable[[RetryPlan], None] | None = None,
        select: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("NDEX Frame - Job Results")
        self.resize(880, 560)
        self.reports = list(reports)
        self.current: JobReport | None = None
        self.retry = retry

        layout = QVBoxLayout(self)

        self.job_list = QListWidget()
        for report in self.reports:
            item = QListWidgetItem(f"{report.headline}")
            self.job_list.addItem(item)
        self.job_list.currentRowChanged.connect(self._show_row)
        layout.addWidget(self.job_list, 1)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.item_view = QPlainTextEdit()
        self.item_view.setReadOnly(True)
        self.item_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.item_view, 2)

        actions = QHBoxLayout()
        self.retry_button = QPushButton("Retry Failed")
        self.retry_button.clicked.connect(self._retry_failed)
        if self.retry is not None:
            actions.addWidget(self.retry_button)
        self.copy_button = QPushButton("Copy Problem Paths")
        self.copy_button.clicked.connect(self._copy_problems)
        self.output_button = QPushButton("Open Output Folder")
        self.output_button.clicked.connect(self._open_destination)
        self.manifest_button = QPushButton("Open Manifest Folder")
        self.manifest_button.clicked.connect(self._open_manifest_folder)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.output_button)
        actions.addWidget(self.manifest_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        if self.reports:
            self.job_list.setCurrentRow(_row_for(self.reports, select))

    def _show_row(self, row: int) -> None:
        if row < 0 or row >= len(self.reports):
            return
        report = self.reports[row]
        self.current = report

        summary = f"{report.type_label} - {report.display_time} - {report.count_summary}"
        if report.cancelled:
            summary = f"{summary} (cancelled)"
        if report.source:
            summary = f"{summary}\nSource: {report.source}"
        if report.destination:
            summary = f"{summary}\nOutput: {report.destination}"
        self.summary_label.setText(summary)
        self.item_view.setPlainText(item_listing(report))

        # Whether those files are still on disk is checked when the button is
        # pressed, not here: a manifest can point at a card since unplugged.
        self.retry_button.setEnabled(self.retry is not None and retryable(report))
        self.copy_button.setEnabled(bool(report.problem_paths()))
        self.output_button.setEnabled(_is_dir(report.destination))

    def _retry_failed(self) -> None:
        """Hand the job back to the main window, which checks the files.

        The window owns the message boxes, so a plan with nothing left on
        disk goes there too and is explained there.
        """
        report, run = self.current, self.retry
        if report is None or run is None or not retryable(report):
            return
        plan = plan_retry(report)
        # Close first: the window takes over from here, and this list is
        # about to be one job out of date.
        self.accept()
        run(plan)

    def _copy_problems(self) -> None:
        if self.current is None:
            return
        paths = self.current.problem_paths()
        if not paths:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("\n".join(paths))

    def _open_destination(self) -> None:
        if self.current is not None and _is_dir(self.current.destination):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current.destination))

    def _open_manifest_folder(self) -> None:
        if self.current is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current.manifest_path.parent)))


def frame_reports(limit: int = HISTORY_LIMIT, select: Path | None = None) -> list[JobReport]:
    """Recent Frame jobs. ``select`` is read in even when it has aged out."""
    reports = recent_reports(apps=("frame",), limit=limit)
    if select is not None and not any(_same_file(item.manifest_path, select) for item in reports):
        selected = read_report(select)
        if selected is not None:
            reports.insert(0, selected)
    return reports


def _row_for(reports: Sequence[JobReport], select: Path | None) -> int:
    if select is None:
        return 0
    for index, report in enumerate(reports):
        if _same_file(report.manifest_path, select):
            return index
    return 0


def _same_file(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def item_listing(report: JobReport) -> str:
    """Items grouped by status, problems first."""
    grouped = report.items_by_status()
    if not grouped:
        return "This job recorded no per-file items."

    blocks = []
    for status, items in grouped.items():
        lines = [f"{status} ({len(items)})"]
        for item in items:
            text = item.path or "(no path)"
            if item.detail:
                text = f"{text}  -  {item.detail}"
            lines.append(f"    {text}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _is_dir(value: str) -> bool:
    return bool(value) and Path(value).is_dir()
