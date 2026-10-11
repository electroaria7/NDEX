"""Qt window showing what recent NDEX Frame jobs did.

The Tk apps share ``ndex_common.report_dialog``; Frame is PySide6, so it reads
the same manifests through ``ndex_common.report`` and renders them here.

It reads manifests and never edits one. It can start a retry, but only by
handing the failed files back to the window that ran the export.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ndex_common.i18n import _
from ndex_common.report import JobItem, JobReport, including, index_of, recent_reports
from ndex_common.retry import RetryPlan, plan_retry, retryable
from ndex_common.theme import DANGER

HISTORY_LIMIT = 30
_YEAR_PREFIX = re.compile(r"^\d{4}-(\d{2}-\d{2} \d{2}:\d{2})$")


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
        self.setWindowTitle(_("NDEX Frame - Job Results"))
        self.resize(880, 560)
        self.reports = list(reports)
        self.current: JobReport | None = None
        self.retry = retry

        layout = QVBoxLayout(self)

        self.job_list = QListWidget()
        for report in self.reports:
            item = QListWidgetItem(job_label(report))
            item.setToolTip(report.headline)
            if report.has_problems:
                item.setForeground(QBrush(QColor(DANGER)))
            self.job_list.addItem(item)
        self.job_list.currentRowChanged.connect(self._show_row)
        layout.addWidget(self.job_list, 1)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.item_table = QTableWidget(0, 2)
        self.item_table.setAccessibleName(_("Files in this job"))
        self.item_table.setHorizontalHeaderLabels([_("File"), _("Result")])
        self.item_table.verticalHeader().setVisible(False)
        self.item_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.item_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.item_table.setWordWrap(False)
        self.item_table.setShowGrid(False)
        self.item_table.setAlternatingRowColors(True)
        self.item_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        header = self.item_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.item_table.setColumnWidth(0, 300)
        layout.addWidget(self.item_table, 2)

        actions = QHBoxLayout()
        self.retry_button = QPushButton(_("Retry Failed"))
        self.retry_button.clicked.connect(self._retry_failed)
        if self.retry is not None:
            actions.addWidget(self.retry_button)
        self.copy_button = QPushButton(_("Copy Problem Paths"))
        self.copy_button.clicked.connect(self._copy_problems)
        self.output_button = QPushButton(_("Open Output Folder"))
        self.output_button.clicked.connect(self._open_destination)
        self.manifest_button = QPushButton(_("Open Manifest Folder"))
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
            self.job_list.setCurrentRow(index_of(self.reports, select))

    def _show_row(self, row: int) -> None:
        if row < 0 or row >= len(self.reports):
            return
        report = self.reports[row]
        self.current = report

        summary = f"{report.type_label} - {report.display_time} - {report.count_summary}"
        if report.cancelled:
            summary = _("{summary} (cancelled)").format(summary=summary)
        if report.source:
            summary = summary + chr(10) + _("Source: {path}").format(path=report.source)
        if report.destination:
            summary = summary + chr(10) + _("Output: {path}").format(path=report.destination)
        self.summary_label.setText(summary)
        self._fill_table(report)

        # Whether those files are still on disk is checked when the button is
        # pressed, not here: a manifest can point at a card since unplugged.
        self.retry_button.setEnabled(self.retry is not None and retryable(report))
        self.copy_button.setEnabled(bool(report.problem_paths()))
        self.output_button.setEnabled(_is_dir(report.destination))

    def _fill_table(self, report: JobReport) -> None:
        rows = item_rows(report)
        table = self.item_table
        table.clearSpans()
        table.setRowCount(len(rows) or 1)
        if not rows:
            empty = QTableWidgetItem(_("This job recorded no per-file items."))
            empty.setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.setItem(0, 0, empty)
            table.setSpan(0, 0, 1, 2)
            return
        red = QBrush(QColor(DANGER))
        for row, (file_text, result_text, problem, tooltip) in enumerate(rows):
            for column, text in enumerate((file_text, result_text)):
                cell = QTableWidgetItem(text)
                cell.setToolTip(tooltip)
                if problem:
                    cell.setForeground(red)
                table.setItem(row, column, cell)

    def _retry_failed(self) -> None:
        """Hand the still-present failed files back to the main window."""
        report, run = self.current, self.retry
        if report is None or run is None or not retryable(report):
            return
        plan = plan_retry(report)
        if not plan.ready:
            # Say so here, where the user is looking, and stay open.
            QMessageBox.information(self, self.windowTitle(), plan.summary)
            return
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
    return including(recent_reports(apps=("frame",), limit=limit), select, apps=("frame",))


def job_label(report: JobReport) -> str:
    """One job-list row, outcome first: ``⚠ 1 failed · Export · 10-10 04:00``."""
    outcome = _("{count} failed").format(count=report.failed_count) if report.has_problems else report.count_summary
    label = _("{type} (cancelled)").format(type=report.type_label) if report.cancelled else report.type_label
    stamp = _YEAR_PREFIX.sub(lambda match: match.group(1), report.display_time)
    text = f"{outcome} · {label} · {stamp}"
    return f"⚠ {text}" if report.has_problems else text


def item_rows(report: JobReport) -> list[tuple[str, str, bool, str]]:
    """``(file, result, is_problem, tooltip)`` per item, problems first."""
    rows = []
    for _status, items in report.items_by_status().items():
        for item in items:
            rows.append(_item_row(item))
    return rows


def _item_row(item: JobItem) -> tuple[str, str, bool, str]:
    tooltip = item.path or _("(no path)")
    if item.destination:
        tooltip = f"{tooltip}" + chr(10) + _("Output: {path}").format(path=item.destination)
    if item.is_problem:
        return f"⚠ {item.name}", item.detail or item.status, True, tooltip
    result = f"{item.status} — {item.detail}" if item.detail else item.status
    return item.name, result, False, tooltip


def item_listing(report: JobReport) -> str:
    """Items grouped by status, problems first (plain text, for copying)."""
    grouped = report.items_by_status()
    if not grouped:
        return _("This job recorded no per-file items.")

    blocks = []
    for status, items in grouped.items():
        lines = [f"{status} ({len(items)})"]
        for item in items:
            text = item.path or _("(no path)")
            if item.detail:
                text = f"{text}  -  {item.detail}"
            lines.append(f"    {text}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _is_dir(value: str) -> bool:
    return bool(value) and Path(value).is_dir()
