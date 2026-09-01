"""Preview-first NDEX Frame application window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ndex_common.branding import NDEX_FRAME_TITLE
from ndex_frame.core.geometry import resolve_canvas
from ndex_frame.core.models import RenderPlan
from ndex_frame.ui.preview_widget import PreviewWidget
from ndex_frame.ui.workspace import WorkspaceController


class MainWindow(QMainWindow):
    def __init__(self, controller: WorkspaceController) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle(NDEX_FRAME_TITLE)
        self.resize(1180, 760)
        self._build_toolbar()
        self._build_workspace()
        self._connect_signals()
        self._sync_controls()
        self._refresh_sources()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Workspace", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.open_files_button = QPushButton("Open Files")
        self.open_folder_button = QPushButton("Open Folder")
        toolbar.addWidget(self.open_files_button)
        toolbar.addWidget(self.open_folder_button)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Frame Preset  "))
        self.frame_preset_combo = QComboBox()
        self.frame_preset_combo.addItem(self.controller.state.working_frame.name)
        toolbar.addWidget(self.frame_preset_combo)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Output Profile  "))
        self.output_profile_combo = QComboBox()
        self.output_profile_combo.addItem(self.controller.state.output_profile.name)
        toolbar.addWidget(self.output_profile_combo)
        self.manage_presets_button = QPushButton("Manage Presets")
        toolbar.addWidget(self.manage_presets_button)

    def _build_workspace(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Images"))
        self.thumbnail_view = QListWidget()
        self.thumbnail_view.setMinimumWidth(190)
        left_layout.addWidget(self.thumbnail_view)

        self.preview_widget = PreviewWidget()

        self.frame_panel = QWidget()
        self.frame_panel.setMinimumWidth(225)
        frame_layout = QFormLayout(self.frame_panel)
        frame_layout.addRow(QLabel("Frame"))
        self.ratio_label = QLabel()
        self.background_label = QLabel()
        frame_layout.addRow("Ratio", self.ratio_label)
        frame_layout.addRow("Background", self.background_label)
        scale_row = QWidget()
        scale_layout = QHBoxLayout(scale_row)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(10, 100)
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 100)
        self.scale_spin.setSuffix("%")
        scale_layout.addWidget(self.scale_slider)
        scale_layout.addWidget(self.scale_spin)
        frame_layout.addRow("Photo Size", scale_row)
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
        splitter.setSizes([210, 730, 240])
        root_layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.output_folder_button = QPushButton("Output Folder")
        self.output_folder_label = QLabel("Not selected")
        self.result_summary_label = QLabel()
        self.export_selected_button = QPushButton("Export Selected")
        self.export_all_button = QPushButton("Export All")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.hide()
        bottom.addWidget(self.output_folder_button)
        bottom.addWidget(self.output_folder_label, 1)
        bottom.addWidget(self.result_summary_label)
        bottom.addWidget(self.export_selected_button)
        bottom.addWidget(self.export_all_button)
        bottom.addWidget(self.cancel_button)
        root_layout.addLayout(bottom)
        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.open_files_button.clicked.connect(self._choose_files)
        self.open_folder_button.clicked.connect(self._choose_folder)
        self.output_folder_button.clicked.connect(self._choose_output_folder)
        self.thumbnail_view.currentItemChanged.connect(self._thumbnail_selected)
        self.scale_slider.valueChanged.connect(self.scale_spin.setValue)
        self.scale_spin.valueChanged.connect(self.scale_slider.setValue)
        self.scale_spin.valueChanged.connect(self._framing_controls_changed)
        self.x_spin.valueChanged.connect(self._framing_controls_changed)
        self.y_spin.valueChanged.connect(self._framing_controls_changed)
        self.preview_widget.framingDragged.connect(self._preview_dragged)
        self.reset_override_button.clicked.connect(self.controller.reset_selected_override)
        self.apply_all_button.clicked.connect(self.controller.apply_current_framing_to_all)
        self.export_selected_button.clicked.connect(self._export_selected)
        self.export_all_button.clicked.connect(self._export_all)
        self.cancel_button.clicked.connect(self.controller.cancel_export)
        self.controller.sourcesChanged.connect(self._refresh_sources)
        self.controller.selectionChanged.connect(lambda _path: self._sync_controls())
        self.controller.previewReady.connect(self._show_preview)
        self.controller.errorOccurred.connect(self.show_nonfatal_error)
        self.controller.busyChanged.connect(self._busy_changed)
        self.controller.exportProgress.connect(self._export_progress)
        self.controller.exportFinished.connect(self._export_finished)

    @Slot()
    def _choose_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, "Open Master Images", "", "Images (*.jpg *.jpeg *.png *.tif *.tiff)")
        if names:
            self.controller.import_paths([Path(name) for name in names])

    @Slot()
    def _choose_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "Open Master Folder")
        if name:
            self.controller.import_paths([Path(name)])

    @Slot()
    def _choose_output_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if name:
            self.controller.state.output_directory = Path(name)
            self.output_folder_label.setText(name)

    @Slot()
    def _refresh_sources(self) -> None:
        selected = self.controller.state.selected_path
        with QSignalBlocker(self.thumbnail_view):
            self.thumbnail_view.clear()
            for source in self.controller.state.sources:
                status = "Modified" if self.controller.state.is_modified(source.path) else "Default"
                item = QListWidgetItem(f"{source.path.name}\n{status}")
                item.setData(Qt.ItemDataRole.UserRole, source.path)
                if source.path == selected:
                    self.thumbnail_view.setCurrentItem(item)
        self._sync_controls()

    @Slot(object, object)
    def _thumbnail_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is not None:
            self.controller.select(current.data(Qt.ItemDataRole.UserRole))

    def _sync_controls(self) -> None:
        state = self.controller.state
        frame = state.working_frame
        self.ratio_label.setText(f"{frame.ratio.width}:{frame.ratio.height}")
        self.background_label.setText(frame.background)
        if state.selected_path is None:
            values = (frame.photo_scale, frame.x, frame.y)
        else:
            values = state.effective_framing(state.selected_path)
        blockers = [QSignalBlocker(control) for control in (self.scale_slider, self.scale_spin, self.x_spin, self.y_spin)]
        self.scale_slider.setValue(round(values[0] * 100))
        self.scale_spin.setValue(round(values[0] * 100))
        self.x_spin.setValue(values[1])
        self.y_spin.setValue(values[2])
        del blockers
        width, height = resolve_canvas(state.output_profile.sizing, frame.ratio)
        self.result_summary_label.setText(
            f"{width}×{height} · {state.output_profile.format.upper()} · {state.output_profile.color_space}"
        )
        enabled = bool(state.sources) and state.output_directory is not None
        self.export_selected_button.setEnabled(enabled and state.selected_path is not None)
        self.export_all_button.setEnabled(enabled)

    @Slot()
    def _framing_controls_changed(self) -> None:
        self.controller.set_selected_framing(
            self.scale_spin.value() / 100.0, self.x_spin.value(), self.y_spin.value()
        )
        self._refresh_sources()

    @Slot(float, float)
    def _preview_dragged(self, x: float, y: float) -> None:
        self.controller.set_selected_framing(self.scale_spin.value() / 100.0, x, y)

    @Slot(object, object, object, object)
    def _show_preview(self, path: Path, image: QImage, plan: RenderPlan, background: str) -> None:
        if path != self.controller.state.selected_path:
            return
        _scale, x, y = self.controller.state.effective_framing(path)
        self.preview_widget.set_preview(QPixmap.fromImage(image), plan, background, x, y)

    def queue_source(self, source: Path) -> None:
        if source.is_dir():
            self.controller.import_paths([source])
        else:
            self.show_nonfatal_error(f"Source folder does not exist: {source}")

    @Slot(str)
    def show_nonfatal_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 10000)

    def _export_selected(self) -> None:
        path = self.controller.state.selected_path
        if path is not None:
            self.controller.start_export([self.controller.state.source(path)])

    def _export_all(self) -> None:
        self.controller.start_export()

    @Slot(bool)
    def _busy_changed(self, busy: bool) -> None:
        exporting = self.controller._export_thread is not None
        self.cancel_button.setVisible(exporting)
        self.export_all_button.setEnabled(not busy and bool(self.controller.state.sources) and self.controller.state.output_directory is not None)
        self.export_selected_button.setEnabled(not busy and self.export_all_button.isEnabled())

    @Slot(object)
    def _export_progress(self, progress: object) -> None:
        self.statusBar().showMessage(f"{progress.source.name} · {progress.index} / {progress.total}")

    @Slot(object)
    def _export_finished(self, result: object) -> None:
        self.cancel_button.hide()
        self.statusBar().showMessage(
            f"Exported {result.exported} · Skipped {result.skipped} · Failed {result.failed}", 15000
        )
        self._sync_controls()
