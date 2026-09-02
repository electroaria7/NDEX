"""Preview-first NDEX Frame application window."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Slot
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ndex_common.branding import APP_ICON_ICO, NDEX_FRAME_TITLE, get_branding_asset_path
from ndex_common.theme import apply_qt_theme
from ndex_frame.core.framing_choices import normalize_hex_color
from ndex_frame.core.geometry import resolve_canvas
from ndex_frame.core.models import AspectRatio, FramePreset, OutputProfile, RenderPlan, SourceItem
from ndex_frame.services.export_job import ExportRequest, ExportResult, plan_export
from ndex_frame.services.presets import PresetStore
from ndex_frame.ui.preset_dialog import (
    ExportCompletionDialog,
    ExportPreflightDialog,
    FramePresetDialog,
    ManagePresetsDialog,
    summarize_preflight,
)
from ndex_frame.ui.framing_widgets import (
    make_background_preset_buttons,
    make_photo_size_preset_buttons,
    make_ratio_preset_buttons,
)
from ndex_frame.ui.preview_widget import PreviewWidget
from ndex_frame.ui.profile_dialog import OutputProfileDialog
from ndex_frame.ui.workspace import WorkspaceController


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller: WorkspaceController,
        preset_store: PresetStore | None = None,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.preset_store = preset_store
        self._interactive_dialogs = True
        self._last_report_dialog: QDialog | None = None
        self.pending_retry = None
        self._retry_paths: list[Path] | None = None
        self.last_export_result: ExportResult | None = None
        self._last_completion_dialog: ExportCompletionDialog | None = None
        self._source_export_status: dict[Path, str] = {}
        self._known_source_paths: set[Path] = set()
        self._export_total = 0
        self._busy = False
        self.handoff_path: Path | None = None
        self.setWindowTitle(NDEX_FRAME_TITLE)
        self.resize(1180, 760)
        apply_qt_theme(self)
        icon_path = get_branding_asset_path(APP_ICON_ICO)
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._build_toolbar()
        self._build_workspace()
        self._reload_preset_combos()
        self._connect_signals()
        self._sync_controls()
        self._refresh_sources()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._interactive_dialogs = False
        self.request_cancel()
        self.controller.shutdown()
        super().closeEvent(event)

    def set_interactive_dialogs(self, enabled: bool) -> None:
        self._interactive_dialogs = enabled

    def sync_output_folder_label(self) -> None:
        directory = self.controller.state.output_directory
        self.output_folder_label.setText("Not selected" if directory is None else str(directory))
        self._sync_controls()

    def refresh_thumbnails(self) -> None:
        self._refresh_sources()

    def request_cancel(self) -> None:
        self.cancel_button.setText("Cancelling…")
        self.controller.cancel_export()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Workspace", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.open_files_button = QPushButton("Open Files")
        self.open_folder_button = QPushButton("Open Folder")
        toolbar.addWidget(self.open_files_button)
        toolbar.addWidget(self.open_folder_button)
        toolbar.addSeparator()
        frame_preset_label = QLabel("Frame Preset  ")
        self.frame_preset_combo = QComboBox()
        frame_preset_label.setBuddy(self.frame_preset_combo)
        self.frame_preset_combo.setAccessibleName("Frame Preset")
        toolbar.addWidget(frame_preset_label)
        toolbar.addWidget(self.frame_preset_combo)
        toolbar.addSeparator()
        output_profile_label = QLabel("Output Profile  ")
        self.output_profile_combo = QComboBox()
        output_profile_label.setBuddy(self.output_profile_combo)
        self.output_profile_combo.setAccessibleName("Output Profile")
        toolbar.addWidget(output_profile_label)
        toolbar.addWidget(self.output_profile_combo)
        self.manage_presets_button = QPushButton("Manage Presets")
        toolbar.addWidget(self.manage_presets_button)
        self.job_results_button = QPushButton("Job Results")
        toolbar.addWidget(self.job_results_button)

    def _build_workspace(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        left = QWidget()
        left.setObjectName("thumbPanel")
        left.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 16, 12, 16)
        left_layout.setSpacing(8)
        images_label = QLabel("Images")
        images_label.setObjectName("sectionLabel")
        self.thumbnail_view = QListWidget()
        images_label.setBuddy(self.thumbnail_view)
        self.thumbnail_view.setAccessibleName("Source Images")
        self.thumbnail_view.setMinimumWidth(190)
        left_layout.addWidget(images_label)
        left_layout.addWidget(self.thumbnail_view)

        self.preview_widget = PreviewWidget()

        self.frame_panel = QWidget()
        self.frame_panel.setObjectName("sidePanel")
        self.frame_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.frame_panel.setMinimumWidth(270)
        frame_layout = QFormLayout(self.frame_panel)
        frame_layout.setContentsMargins(16, 16, 16, 16)
        frame_layout.setHorizontalSpacing(10)
        frame_layout.setVerticalSpacing(10)
        frame_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        frame_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        frame_heading = QLabel("Frame")
        frame_heading.setObjectName("sectionLabel")
        frame_layout.addRow(frame_heading)
        ratio_row = QWidget()
        ratio_layout = QHBoxLayout(ratio_row)
        ratio_layout.setContentsMargins(0, 0, 0, 0)
        self.ratio_width_spin = QSpinBox()
        self.ratio_height_spin = QSpinBox()
        for spin in (self.ratio_width_spin, self.ratio_height_spin):
            spin.setRange(1, 99)
        self.ratio_width_spin.setAccessibleName("Ratio width")
        self.ratio_height_spin.setAccessibleName("Ratio height")
        ratio_layout.addWidget(self.ratio_width_spin)
        ratio_layout.addWidget(QLabel(":"))
        ratio_layout.addWidget(self.ratio_height_spin)
        ratio_layout.addStretch(1)
        self.ratio_label = QLabel()
        frame_layout.addRow("Ratio", ratio_row)
        ratio_presets, self.ratio_preset_buttons = make_ratio_preset_buttons(self._apply_ratio_preset)
        frame_layout.addRow("", ratio_presets)
        background_presets, self.background_preset_buttons, self.custom_background_button = (
            make_background_preset_buttons(self._apply_background, self._pick_background)
        )
        self.background_label = QLabel()
        self.background_label.setObjectName("mutedLabel")
        # Keep the label readable and give swatches + Custom a full-width row.
        frame_layout.addRow("Background", self.background_label)
        frame_layout.addRow("", background_presets)
        scale_row = QWidget()
        scale_layout = QHBoxLayout(scale_row)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setAccessibleName("Photo Size")
        self.scale_slider.setRange(10, 100)
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 100)
        self.scale_spin.setSuffix("%")
        scale_layout.addWidget(self.scale_slider)
        scale_layout.addWidget(self.scale_spin)
        size_presets, self.photo_size_preset_buttons = make_photo_size_preset_buttons(
            self._apply_photo_size_preset
        )
        frame_layout.addRow("Photo Size", scale_row)
        frame_layout.addRow("", size_presets)
        self.x_spin = QDoubleSpinBox()
        self.y_spin = QDoubleSpinBox()
        for spin in (self.x_spin, self.y_spin):
            spin.setRange(-1.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
        frame_layout.addRow("X", self.x_spin)
        frame_layout.addRow("Y", self.y_spin)
        self.reset_override_button = QPushButton("Reset Override")
        self.apply_all_button = QPushButton("Apply Current Framing to All")
        self.save_frame_button = QPushButton("Save as Frame Preset")
        frame_layout.addRow(self.reset_override_button)
        frame_layout.addRow(self.apply_all_button)
        frame_layout.addRow(self.save_frame_button)

        splitter.addWidget(left)
        splitter.addWidget(self.preview_widget)
        splitter.addWidget(self.frame_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([210, 690, 280])
        root_layout.addWidget(splitter, 1)

        footer = QWidget()
        footer.setObjectName("footerBar")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(16, 10, 16, 12)
        bottom.setSpacing(10)
        self.output_folder_button = QPushButton("Output Folder")
        self.output_folder_label = QLabel("Not selected")
        self.output_folder_label.setObjectName("mutedLabel")
        self.result_summary_label = QLabel()
        self.result_summary_label.setObjectName("mutedLabel")
        self.export_progress_bar = QProgressBar()
        self.export_progress_bar.setAccessibleName("Export progress")
        self.export_progress_bar.setTextVisible(True)
        self.export_progress_bar.setMinimumWidth(180)
        self.export_progress_bar.hide()
        self.export_selected_button = QPushButton("Export Selected")
        self.export_all_button = QPushButton("Export All")
        self.export_all_button.setObjectName("primaryButton")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.hide()
        bottom.addWidget(self.output_folder_button)
        bottom.addWidget(self.output_folder_label, 1)
        bottom.addWidget(self.result_summary_label)
        bottom.addWidget(self.export_progress_bar, 1)
        bottom.addWidget(self.export_selected_button)
        bottom.addWidget(self.export_all_button)
        bottom.addWidget(self.cancel_button)
        root_layout.addWidget(footer)
        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.open_files_button.clicked.connect(self._choose_files)
        self.open_folder_button.clicked.connect(self._choose_folder)
        self.output_folder_button.clicked.connect(self._choose_output_folder)
        self.manage_presets_button.clicked.connect(self._manage_presets)
        self.job_results_button.clicked.connect(self._open_job_results)
        self.save_frame_button.clicked.connect(self._save_frame_preset)
        self.frame_preset_combo.currentIndexChanged.connect(self._frame_preset_chosen)
        self.output_profile_combo.currentIndexChanged.connect(self._output_profile_chosen)
        self.thumbnail_view.currentItemChanged.connect(self._thumbnail_selected)
        self.scale_slider.valueChanged.connect(self.scale_spin.setValue)
        self.scale_spin.valueChanged.connect(self.scale_slider.setValue)
        self.scale_spin.valueChanged.connect(self._framing_controls_changed)
        self.x_spin.valueChanged.connect(self._framing_controls_changed)
        self.y_spin.valueChanged.connect(self._framing_controls_changed)
        self.ratio_width_spin.valueChanged.connect(self._ratio_changed)
        self.ratio_height_spin.valueChanged.connect(self._ratio_changed)
        self.preview_widget.framingDragged.connect(self._preview_dragged)
        self.reset_override_button.clicked.connect(self._reset_override)
        self.apply_all_button.clicked.connect(self._apply_all)
        self.export_selected_button.clicked.connect(self._export_selected)
        self.export_all_button.clicked.connect(self._export_all)
        self.cancel_button.clicked.connect(self.request_cancel)
        self.controller.sourcesChanged.connect(self._sources_changed)
        self.controller.selectionChanged.connect(lambda _path: self._sync_controls())
        self.controller.previewReady.connect(self._show_preview)
        self.controller.errorOccurred.connect(self.show_nonfatal_error)
        self.controller.busyChanged.connect(self._busy_changed)
        self.controller.exportProgress.connect(self._export_progress)
        self.controller.exportFinished.connect(self._export_finished)

    def _reload_preset_combos(self) -> None:
        frames: list[FramePreset]
        outputs: list[OutputProfile]
        if self.preset_store is None:
            frames = [self.controller.state.working_frame]
            outputs = [self.controller.state.output_profile]
        else:
            frames = list(self.preset_store.list_frames())
            outputs = list(self.preset_store.list_outputs())
        with QSignalBlocker(self.frame_preset_combo), QSignalBlocker(self.output_profile_combo):
            self.frame_preset_combo.clear()
            for frame in frames:
                self.frame_preset_combo.addItem(frame.name, frame)
            self.output_profile_combo.clear()
            for output in outputs:
                self.output_profile_combo.addItem(output.name, output)
            self._select_combo(self.frame_preset_combo, self.controller.state.working_frame.id)
            self._select_combo(self.output_profile_combo, self.controller.state.output_profile.id)
        frame = self.frame_preset_combo.currentData()
        output = self.output_profile_combo.currentData()
        if frame is not None:
            self.controller.state.working_frame = frame
        if output is not None:
            self.controller.state.output_profile = output

    @staticmethod
    def _select_combo(combo: QComboBox, preset_id: str) -> None:
        for index in range(combo.count()):
            preset = combo.itemData(index)
            if preset is not None and preset.id == preset_id:
                combo.setCurrentIndex(index)
                return

    @Slot()
    def _frame_preset_chosen(self) -> None:
        preset = self.frame_preset_combo.currentData()
        if preset is None:
            return
        self.controller.state.working_frame = preset
        self._request_selected_preview()
        self._sync_controls()

    @Slot()
    def _output_profile_chosen(self) -> None:
        profile = self.output_profile_combo.currentData()
        if profile is None:
            return
        self.controller.state.output_profile = profile
        self._request_selected_preview()
        self._sync_controls()

    def _request_selected_preview(self) -> None:
        if self.controller.state.selected_path is not None:
            self.controller.request_preview(self.controller.state.selected_path)

    @Slot()
    def _manage_presets(self) -> None:
        chooser = ManagePresetsDialog(self)
        if self._interactive_dialogs:
            if chooser.exec() != QDialog.DialogCode.Accepted:
                return
        elif chooser.choice is None:
            return
        if chooser.choice == "frame":
            self._edit_frame_preset()
        elif chooser.choice == "output":
            self._edit_output_profile()

    @Slot()
    def _save_frame_preset(self) -> None:
        current = replace(
            self.controller.state.working_frame,
            photo_scale=self.scale_spin.value() / 100.0,
            x=self.x_spin.value(),
            y=self.y_spin.value(),
        )
        self._edit_frame_preset(current)

    def _edit_frame_preset(self, preset: FramePreset | None = None) -> None:
        dialog = FramePresetDialog(
            preset or self.controller.state.working_frame,
            self,
            store=self.preset_store,
        )
        if self._interactive_dialogs:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self.preset_store is not None:
                frames = {item.id: item for item in self.preset_store.list_frames()}
                self.controller.state.working_frame = frames.get(dialog.build_preset().id) or self.preset_store.default_frame()
        self._reload_preset_combos()
        self._sync_controls()
        self._request_selected_preview()

    def _edit_output_profile(self) -> None:
        dialog = OutputProfileDialog(
            self.controller.state.output_profile,
            self.controller.state.working_frame.ratio,
            self,
            store=self.preset_store,
        )
        if self._interactive_dialogs:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self.preset_store is not None:
                outputs = {item.id: item for item in self.preset_store.list_outputs()}
                self.controller.state.output_profile = (
                    outputs.get(dialog.build_profile().id) or self.preset_store.default_output()
                )
        self._reload_preset_combos()
        self._sync_controls()
        self._request_selected_preview()

    @Slot()
    def _open_job_results(self) -> QDialog | None:
        """Show what recent Frame exports wrote, skipped, or failed on."""
        from ndex_frame.ui.report_dialog import FrameJobReportDialog, frame_reports

        reports = frame_reports()
        if not reports:
            self.show_nonfatal_error("No export results recorded yet.")
            return None
        dialog = FrameJobReportDialog(reports, self, retry=self._retry_export)
        self._last_report_dialog = dialog
        if self._interactive_dialogs:
            dialog.exec()
        return dialog

    def _retry_export(self, plan) -> None:
        """Export again the files an earlier job failed on.

        The output folder comes from that job, not from the one showing now:
        a retry belongs with the pictures it was meant to sit beside.
        """
        if not plan.ready:
            self.show_nonfatal_error(plan.summary)
            return
        if self._busy or self.controller._export_thread is not None:
            self.show_nonfatal_error("Wait for the running job to finish, then retry.")
            return
        paths = list(plan.paths)
        destination = Path(plan.report.destination) if plan.report.destination else None
        if destination is None or not destination.is_dir():
            self.show_nonfatal_error(
                f"That job's output folder is gone: {plan.report.destination}"
            )
            return
        if self._interactive_dialogs:
            answer = QMessageBox.question(
                self,
                "Retry Failed",
                plan.question(
                    destination_label="Output", note="Frame opens just these files."
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self.controller.state.output_directory = destination
        self.sync_output_folder_label()
        self.pending_retry = plan

        loaded = {
            os.path.normcase(str(source.path)): source
            for source in self.controller.state.sources
        }
        already_open = [
            loaded[key]
            for key in (os.path.normcase(str(path)) for path in paths)
            if key in loaded
        ]
        if len(already_open) == len(paths):
            self._export_retry(already_open)
            return

        # Some are not open. Load exactly those files; _sources_changed picks
        # the export up once the import lands.
        self._retry_paths = paths
        self.controller.import_paths(paths)

    def _export_retry(self, sources: list[SourceItem]) -> None:
        try:
            self.confirm_export(sources, "rename")
        except Exception as error:
            self._drop_retry(f"Retry stopped: {error or error.__class__.__name__}")

    def _drop_retry(self, message: str) -> None:
        """Forget a retry that cannot go ahead, and say so.

        Otherwise the flag would fire on the next unrelated import and the
        next export would be recorded as a retry of the wrong job.
        """
        self._retry_paths = None
        self.pending_retry = None
        self.show_nonfatal_error(message)

    @Slot()
    def _choose_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, "Open Master Images", "", "Images (*.jpg *.jpeg *.png *.tif *.tiff)")
        if names:
            self.handoff_path = None
            self.controller.import_paths([Path(name) for name in names])

    @Slot()
    def _choose_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "Open Master Folder")
        if name:
            self.handoff_path = None
            self.controller.import_paths([Path(name)])

    @Slot()
    def _choose_output_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if name:
            self.controller.state.output_directory = Path(name)
            self.sync_output_folder_label()

    @Slot()
    def _sources_changed(self) -> None:
        current = {source.path for source in self.controller.state.sources}
        if current != self._known_source_paths:
            self._source_export_status.clear()
            self._known_source_paths = current
        self._refresh_sources()
        if self._retry_paths is None:
            return
        # Only the retry's own import may start the export. Anything else
        # arriving first (a drop, a handoff, Apply to all) means the
        # workspace is no longer what the retry was about.
        wanted = {os.path.normcase(str(path)) for path in self._retry_paths}
        loaded = {os.path.normcase(str(source.path)) for source in self.controller.state.sources}
        self._retry_paths = None
        if loaded != wanted:
            self._drop_retry("Retry stopped: different files were opened.")
            return
        # Let the import finish emitting before the export claims the UI.
        QTimer.singleShot(0, self._start_pending_retry)

    def _start_pending_retry(self) -> None:
        if self.pending_retry is None:
            return
        self._export_retry(list(self.controller.state.sources))

    def _status_for(self, path: Path) -> str:
        export_status = self._source_export_status.get(path)
        if export_status == "Error":
            return "Error"
        if export_status == "Exported":
            return "Exported"
        if self.controller.state.is_modified(path):
            return "Modified"
        return "Default"

    @Slot()
    def _refresh_sources(self) -> None:
        selected = self.controller.state.selected_path
        with QSignalBlocker(self.thumbnail_view):
            self.thumbnail_view.clear()
            for source in self.controller.state.sources:
                item = QListWidgetItem(f"{source.path.name}\n{self._status_for(source.path)}")
                item.setData(Qt.ItemDataRole.UserRole, source.path)
                self.thumbnail_view.addItem(item)
                if source.path == selected:
                    self.thumbnail_view.setCurrentItem(item)
        self._sync_controls()

    @Slot(object, object)
    def _thumbnail_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is not None:
            self.controller.select(current.data(Qt.ItemDataRole.UserRole))

    def _output_folder_ready(self) -> bool:
        directory = self.controller.state.output_directory
        return directory is not None and directory.is_dir()

    def _sync_controls(self) -> None:
        state = self.controller.state
        frame = state.working_frame
        self.ratio_label.setText(f"{frame.ratio.width}:{frame.ratio.height}")
        self.background_label.setText(frame.background)
        blockers = [
            QSignalBlocker(control)
            for control in (self.scale_slider, self.scale_spin, self.x_spin, self.y_spin, self.ratio_width_spin, self.ratio_height_spin)
        ]
        self.ratio_width_spin.setValue(frame.ratio.width)
        self.ratio_height_spin.setValue(frame.ratio.height)
        if state.selected_path is None:
            values = (frame.photo_scale, frame.x, frame.y)
        else:
            values = state.effective_framing(state.selected_path)
        self.scale_slider.setValue(round(values[0] * 100))
        self.scale_spin.setValue(round(values[0] * 100))
        self.x_spin.setValue(values[1])
        self.y_spin.setValue(values[2])
        del blockers
        width, height = resolve_canvas(state.output_profile.sizing, frame.ratio)
        self.result_summary_label.setText(
            f"{width}×{height} · {state.output_profile.format.upper()} · {state.output_profile.color_space}"
        )
        can_export = (not self._busy) and self._output_folder_ready() and bool(state.sources)
        self.export_all_button.setEnabled(can_export)
        self.export_selected_button.setEnabled(can_export and state.selected_path is not None)

    @Slot()
    def _reset_override(self) -> None:
        self.controller.reset_selected_override()
        self._refresh_sources()

    @Slot()
    def _apply_all(self) -> None:
        self.controller.apply_current_framing_to_all()
        self._refresh_sources()

    def _ratio_changed(self) -> None:
        self.controller.update_working_frame(
            ratio=AspectRatio(self.ratio_width_spin.value(), self.ratio_height_spin.value())
        )
        self._sync_controls()

    def _apply_ratio_preset(self, ratio: AspectRatio) -> None:
        self.controller.update_working_frame(ratio=ratio)
        self._sync_controls()

    def _apply_background(self, color: str) -> None:
        normalized = normalize_hex_color(color)
        if normalized is None:
            self._sync_controls()
            return
        self.controller.update_working_frame(background=normalized)
        self._sync_controls()

    def _pick_background(self) -> None:
        if not self._interactive_dialogs:
            return
        current = QColor(self.controller.state.working_frame.background)
        chosen = QColorDialog.getColor(current, self, "Frame background")
        if chosen.isValid():
            self._apply_background(chosen.name())

    def _apply_photo_size_preset(self, percent: int) -> None:
        self.scale_spin.setValue(percent)

    @Slot()
    def _framing_controls_changed(self) -> None:
        self.controller.set_selected_framing(
            self.scale_spin.value() / 100.0, self.x_spin.value(), self.y_spin.value()
        )
        self._refresh_sources()

    @Slot(float, float)
    def _preview_dragged(self, x: float, y: float) -> None:
        self.controller.set_selected_framing(self.scale_spin.value() / 100.0, x, y)
        self._refresh_sources()

    @Slot(object, object, object, object)
    def _show_preview(self, path: Path, image: QImage, plan: RenderPlan, background: str) -> None:
        if path != self.controller.state.selected_path:
            return
        _scale, x, y = self.controller.state.effective_framing(path)
        self.preview_widget.set_preview(QPixmap.fromImage(image), plan, background, x, y)

    def queue_source(self, source: Path) -> None:
        self.handoff_path = None
        if source.is_dir():
            self.controller.import_paths([source])
        else:
            self.show_nonfatal_error(f"Source folder does not exist: {source}")

    def queue_handoff(self, handoff: Path) -> None:
        from ndex_common.manifest import handoff_files, load_manifest

        path = Path(handoff)
        payload = load_manifest(path)
        if payload is None:
            self.handoff_path = None
            self.show_nonfatal_error(f"Could not read handoff: {path}")
            return
        files = handoff_files(payload)
        if not files:
            self.handoff_path = None
            self.show_nonfatal_error("Handoff has no JPG/PNG/TIFF files Frame can import.")
            return
        self.handoff_path = path
        self.controller.import_paths(files)

    @Slot(str)
    def show_nonfatal_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 10000)

    def _export_request(
        self, sources: list[SourceItem] | None, collision_policy: str
    ) -> ExportRequest:
        selected = tuple(sources if sources is not None else self.controller.state.sources)
        directory = self.controller.state.output_directory
        if directory is None:
            raise ValueError("Output folder is unavailable.")
        return ExportRequest(
            selected,
            directory,
            self.controller.state.working_frame,
            self.controller.state.output_profile,
            tuple(self.controller.state.overrides.values()),
            collision_policy,  # type: ignore[arg-type]
        )

    def preflight(self, sources: list[SourceItem] | None = None):
        return summarize_preflight(plan_export(self._export_request(sources, "skip")))

    def confirm_export(
        self,
        sources: list[SourceItem] | None = None,
        collision_policy: str = "rename",
    ) -> None:
        selected = list(sources) if sources is not None else list(self.controller.state.sources)
        plan_export(self._export_request(selected, collision_policy))
        self.last_export_result = None
        self._export_total = len(selected)
        self.export_progress_bar.setRange(0, max(1, len(selected)))
        self.export_progress_bar.setValue(0)
        self.export_progress_bar.setFormat("%v / %m")
        self.export_progress_bar.show()
        self.controller.start_export(selected, collision_policy)

    def _prompt_export(self, sources: list[SourceItem] | None) -> None:
        if not self._output_folder_ready() or not self.controller.state.sources:
            return
        try:
            counts = self.preflight(sources)
        except Exception as error:
            self.show_nonfatal_error(str(error) or error.__class__.__name__)
            return
        dialog = ExportPreflightDialog(counts, has_conflicts=counts.conflicted > 0, parent=self)
        if self._interactive_dialogs:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
        elif dialog.collision_policy() is None:
            dialog.rename_radio.setChecked(True)
        policy = dialog.collision_policy()
        if policy not in {"skip", "rename"}:
            return
        self.confirm_export(sources, policy)

    def _export_selected(self) -> None:
        path = self.controller.state.selected_path
        if path is not None:
            self._prompt_export([self.controller.state.source(path)])

    def _export_all(self) -> None:
        self._prompt_export(None)

    @Slot(bool)
    def _busy_changed(self, busy: bool) -> None:
        self._busy = busy
        exporting = self.controller._export_thread is not None
        self.cancel_button.setVisible(exporting)
        if exporting:
            self.export_progress_bar.show()
        else:
            self.export_progress_bar.hide()
        if not exporting:
            self.cancel_button.setText("Cancel")
        if not busy and not exporting and self._retry_paths is not None:
            # The import ended without delivering sources: it failed.
            self._drop_retry("Retry stopped: the files could not be opened.")
        self._sync_controls()

    @Slot(object)
    def _export_progress(self, progress: object) -> None:
        total = max(1, int(getattr(progress, "total", 1) or 1))
        index = max(0, min(total, int(getattr(progress, "index", 0) or 0)))
        name = getattr(getattr(progress, "source", None), "name", "")
        self.export_progress_bar.setRange(0, total)
        self.export_progress_bar.setValue(index)
        self.export_progress_bar.setFormat(f"{name} · %v / %m" if name else "%v / %m")
        self.export_progress_bar.show()
        self.statusBar().showMessage(f"{name} · {index} / {total}".strip(" ·"))

    @Slot(object)
    def _export_finished(self, result: object) -> None:
        self.last_export_result = result  # type: ignore[assignment]
        self.cancel_button.hide()
        self.cancel_button.setText("Cancel")
        self.export_progress_bar.hide()
        self.export_progress_bar.reset()
        for item in getattr(result, "items", ()):
            if item.state == "exported":
                self._source_export_status[item.source] = "Exported"
            elif item.state == "failed":
                self._source_export_status[item.source] = "Error"
        cancelled = 0
        if getattr(result, "cancelled", False):
            cancelled = max(
                0,
                self._export_total - result.exported - result.skipped - result.failed,
            )
        dialog = ExportCompletionDialog(
            result, cancelled, self.controller.state.output_directory, self
        )
        self._last_completion_dialog = dialog
        summary = dialog.summary_label.text()
        self.statusBar().showMessage(summary, 15000)
        if self._interactive_dialogs:
            dialog.exec()
        self._refresh_sources()
