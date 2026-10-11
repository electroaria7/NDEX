"""Preview-first NDEX Frame application window."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPoint, QSignalBlocker, QSize, Qt, QTimer, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QImage,
    QKeyEvent,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ndex_common.i18n import _, ngettext
from ndex_common.branding import APP_ICON_ICO, NDEX_FRAME_TITLE, get_branding_asset_path
from ndex_common.retry import path_key
from ndex_common.theme import DANGER, TEXT_PRIMARY, apply_qt_theme
from ndex_frame.core.framing_choices import normalize_hex_color
from ndex_frame.core.messages import describe_error, raw_hint, warning_text
from ndex_frame.core.geometry import resolve_canvas
from ndex_frame.core.models import AspectRatio, FramePreset, OutputProfile, RenderPlan, SourceItem
from ndex_frame.services.export_job import ExportRequest, ExportResult, plan_export
from ndex_frame.services.importer import RAW_SUFFIXES
from ndex_frame.services.presets import PresetStore
from ndex_frame.services.thumbnails import ThumbnailCache
from ndex_frame.ui.elided_label import ElidedLabel
from ndex_frame.ui.preset_dialog import (
    ExportCompletionDialog,
    ExportPreflightDialog,
    FramePresetDialog,
    colour_notes,
    completion_title,
    describe_preflight,
    summarize_preflight,
)
from ndex_frame.ui.framing_widgets import (
    make_background_preset_buttons,
    make_photo_size_preset_buttons,
    make_ratio_preset_buttons,
)
from ndex_frame.ui.presets_manager import PresetsManagerDialog
from ndex_frame.ui.preview_widget import PreviewWidget
from ndex_frame.ui.profile_dialog import OutputProfileDialog
from ndex_frame.ui.thumbnail_loader import THUMBNAIL_SIZE, ThumbnailLoader
from ndex_frame.ui.workspace import WorkspaceController


# Status words are stored in English and translated when drawn (see _status_label).
_STATUS_WORDS = (_("Default"), _("Modified"), _("Exported"), _("Error"), _("Cancelled"))


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller: WorkspaceController,
        preset_store: PresetStore | None = None,
        thumbnail_cache: ThumbnailCache | None = None,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.preset_store = preset_store
        self._interactive_dialogs = True
        self._last_report_dialog: QDialog | None = None
        self.pending_retry = None
        # True while the retry's own import is in flight; the export starts
        # when that import lands and nothing else has taken the workspace.
        self._retry_importing = False
        self._retry_previous_output: Path | None = None
        self.last_export_result: ExportResult | None = None
        self._last_completion_dialog: ExportCompletionDialog | None = None
        self._last_preflight_dialog: ExportPreflightDialog | None = None
        self._source_export_status: dict[Path, str] = {}
        self._known_source_paths: set[Path] = set()
        self._export_total = 0
        self._busy = False
        self._close_pending = False
        self._close_ready = False
        self.handoff_path: Path | None = None
        self._last_presets_dialog: PresetsManagerDialog | None = None
        self._frame_chosen_in_manager = False
        self._item_by_path: dict[Path, QListWidgetItem] = {}
        ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
        self.thumbnail_loader = ThumbnailLoader(
            thumbnail_cache or ThumbnailCache(controller.preview_cache.root / "thumbs"),
            device_pixel_ratio=ratio,
            parent=self,
        )
        self._thumbnail_placeholder = self._make_thumbnail_placeholder()
        self._thumbnail_timer = QTimer(self)
        self._thumbnail_timer.setSingleShot(True)
        self._thumbnail_timer.setInterval(30)
        self._thumbnail_timer.timeout.connect(self.load_visible_thumbnails)
        self.setWindowTitle(NDEX_FRAME_TITLE)
        self.resize(1180, 760)
        self.setAcceptDrops(True)
        apply_qt_theme(self)
        icon_path = get_branding_asset_path(APP_ICON_ICO)
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._build_toolbar()
        self._build_workspace()
        self._fit_minimum_width_to_toolbar()
        self._reload_preset_combos()
        self._connect_signals()
        self._install_shortcuts()
        self._sync_controls()
        self._refresh_sources()

    def teardown(self) -> bool:
        """Stop every background worker and wait for it, then close the window.

        Synchronous (no event loop needed): once it returns, no thumbnail, preview,
        import or export thread is alive, so cache folders can be removed safely.
        """
        self._interactive_dialogs = False
        self.request_cancel()
        self.thumbnail_loader.shutdown()
        clean = self.controller.shutdown_and_wait()
        self._close_ready = True
        self.close()
        return clean

    def closeEvent(self, event: QCloseEvent) -> None:
        # Thumbnail jobs are short; never leave them running past the window.
        self.thumbnail_loader.shutdown()
        if self._close_ready:
            self.thumbnail_loader.shutdown()
            super().closeEvent(event)
            return
        self._interactive_dialogs = False
        self._close_pending = True
        self.request_cancel()
        if self.controller.shutdown():
            self._close_ready = True
            self.thumbnail_loader.shutdown()
            super().closeEvent(event)
        else:
            self.setEnabled(False)
            self.statusBar().showMessage(_("Closing after the current file finishes…"))
            event.ignore()

    @Slot()
    def _finish_close(self) -> None:
        if self._close_pending:
            self._close_ready = True
            self.close()

    def set_interactive_dialogs(self, enabled: bool) -> None:
        self._interactive_dialogs = enabled

    def sync_output_folder_label(self) -> None:
        self._sync_controls()

    def _update_output_folder_label(self) -> None:
        directory = self.controller.state.output_directory
        label = self.output_folder_label
        if directory is None:
            label.setText(_("Output folder: Not selected — choose where framed photos go"))
            label.setToolTip("")
            label.setStyleSheet("")
        elif not directory.is_dir():
            label.setText(_("Output folder: {folder} (folder not found)").format(folder=directory))
            label.setToolTip(str(directory))
            label.setStyleSheet(f"color: {DANGER};")
        else:
            label.setText(_("Output folder: {folder}").format(folder=directory))
            label.setToolTip(str(directory))
            label.setStyleSheet("")

    def refresh_thumbnails(self) -> None:
        self._refresh_sources()

    def request_cancel(self) -> None:
        self.cancel_button.setText(_("Stopping…"))
        self.controller.cancel_export()

    def _install_shortcuts(self) -> None:
        """Keyboard routes. Buttons carry their own shortcuts so a disabled one stays inert."""
        self.open_files_button.setShortcut(QKeySequence("Ctrl+O"))
        self.open_folder_button.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.export_all_button.setShortcut(QKeySequence("Ctrl+E"))
        self.export_selected_button.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.job_results_button.setShortcut(QKeySequence("Ctrl+J"))
        self.open_files_button.setToolTip(_("Open photos (Ctrl+O)"))
        self.open_folder_button.setToolTip(_("Open a folder of photos (Ctrl+Shift+O)"))
        self.job_results_button.setToolTip(_("See what recent exports wrote and failed on (Ctrl+J)"))
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape_shortcut.activated.connect(self._escape_pressed)

    @Slot()
    def _escape_pressed(self) -> None:
        if self.controller._export_thread is not None and self.cancel_button.isEnabled():
            self.request_cancel()

    def step_selection(self, delta: int) -> bool:
        """Move to the previous (-1) or next (+1) photo in the list."""
        count = self.thumbnail_view.count()
        if count == 0:
            return False
        row = self.thumbnail_view.currentRow()
        target = max(0, min(count - 1, (row if row >= 0 else 0) + delta))
        if target == row:
            return False
        self.thumbnail_view.setCurrentRow(target)
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Widgets that use the arrows (list, spin boxes, sliders, combos) handle
        # them first; what reaches the window steps through the photos.
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            key = event.key()
            step = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1}.get(key)
            if step is None and not self.thumbnail_view.hasFocus():
                step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(key)
            if step is not None:
                self.step_selection(step)
                event.accept()
                return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and self.controller._export_thread is None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self.import_dropped(paths)
        event.acceptProposedAction()

    def import_dropped(self, paths: list[Path]) -> None:
        """Files or folders dropped on the window open like Open Files / Open Folder."""
        paths = [path for path in paths if path.exists()]
        if not paths:
            return
        if self.controller._export_thread is not None:
            self.show_nonfatal_error(_("Wait for the export to finish before opening more photos."))
            return
        self.handoff_path = None
        folder = paths[0] if len(paths) == 1 and paths[0].is_dir() else None
        self.controller.import_paths(paths, origin=folder.name if folder else "")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar(_("Workspace"), self)
        self.toolbar = toolbar
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.open_files_button = QPushButton(_("Open Files"))
        self.open_folder_button = QPushButton(_("Open Folder"))
        toolbar.addWidget(self.open_files_button)
        toolbar.addWidget(self.open_folder_button)
        toolbar.addSeparator()
        frame_preset_label = QLabel(_("Frame "))
        self.frame_preset_combo = QComboBox()
        frame_preset_label.setBuddy(self.frame_preset_combo)
        self.frame_preset_combo.setAccessibleName(_("Frame Preset"))
        tip = _("The border, background and aspect ratio around each photo. (edited) means you changed it.")
        frame_preset_label.setToolTip(tip)
        self.frame_preset_combo.setToolTip(tip)
        toolbar.addWidget(frame_preset_label)
        toolbar.addWidget(self.frame_preset_combo)
        toolbar.addSeparator()
        output_profile_label = QLabel(_("Output "))
        self.output_profile_combo = QComboBox()
        output_profile_label.setBuddy(self.output_profile_combo)
        self.output_profile_combo.setAccessibleName(_("Output Profile"))
        tip = _("How big the finished files are and which format they are saved in.")
        output_profile_label.setToolTip(tip)
        self.output_profile_combo.setToolTip(tip)
        for combo, characters in ((self.frame_preset_combo, 14), (self.output_profile_combo, 14)):
            # Size to a few characters, not the longest preset name, so the toolbar fits.
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(characters)
        for label in (frame_preset_label, output_profile_label):
            # The theme's muted grey is too faint on the white toolbar.
            label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        toolbar.addWidget(output_profile_label)
        toolbar.addWidget(self.output_profile_combo)
        self.manage_presets_button = QPushButton(_("Manage Presets"))
        toolbar.addWidget(self.manage_presets_button)
        self.job_results_button = QPushButton(_("Job Results"))
        toolbar.addWidget(self.job_results_button)

    def _fit_minimum_width_to_toolbar(self) -> None:
        """Never let the window get narrower than its toolbar (no » overflow menu)."""
        self.toolbar.adjustSize()
        needed = self.toolbar.sizeHint().width() + 8
        self.setMinimumWidth(max(self.minimumSizeHint().width(), needed))

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
        self.images_label = QLabel(_("Images"))
        self.images_label.setObjectName("sectionLabel")
        self.thumbnail_view = QListWidget()
        self.images_label.setBuddy(self.thumbnail_view)
        self.thumbnail_view.setAccessibleName(_("Source Images"))
        self.thumbnail_view.setMinimumWidth(190)
        self.thumbnail_view.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.thumbnail_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbnail_view.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self.thumbnail_view.setUniformItemSizes(True)
        self.thumbnail_view.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.thumbnail_view.verticalScrollBar().setSingleStep(24)
        left_layout.addWidget(self.images_label)
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
        frame_heading = QLabel(_("All photos"))
        frame_heading.setObjectName("sectionLabel")
        frame_heading.setToolTip(_("Ratio and background apply to every photo."))
        frame_layout.addRow(frame_heading)
        ratio_row = QWidget()
        ratio_layout = QHBoxLayout(ratio_row)
        ratio_layout.setContentsMargins(0, 0, 0, 0)
        self.ratio_width_spin = QSpinBox()
        self.ratio_height_spin = QSpinBox()
        for spin in (self.ratio_width_spin, self.ratio_height_spin):
            spin.setRange(1, 99)
        self.ratio_width_spin.setAccessibleName(_("Ratio width"))
        self.ratio_height_spin.setAccessibleName(_("Ratio height"))
        ratio_layout.addWidget(self.ratio_width_spin)
        ratio_layout.addWidget(QLabel(":"))
        ratio_layout.addWidget(self.ratio_height_spin)
        ratio_layout.addStretch(1)
        self.ratio_label = QLabel()
        frame_layout.addRow(_("Ratio"), ratio_row)
        ratio_presets, self.ratio_preset_buttons = make_ratio_preset_buttons(self._apply_ratio_preset)
        frame_layout.addRow("", ratio_presets)
        background_presets, self.background_preset_buttons, self.custom_background_button = (
            make_background_preset_buttons(self._apply_background, self._pick_background)
        )
        self.background_label = QLabel()
        self.background_label.setObjectName("mutedLabel")
        # Keep the label readable and give swatches + Custom a full-width row.
        frame_layout.addRow(_("Background"), self.background_label)
        frame_layout.addRow("", background_presets)
        selected_heading = QLabel(_("Selected photo"))
        selected_heading.setObjectName("sectionLabel")
        selected_heading.setContentsMargins(0, 12, 0, 0)
        selected_heading.setToolTip(_("Photo size and position apply only to the selected photo."))
        frame_layout.addRow(selected_heading)
        scale_row = QWidget()
        scale_layout = QHBoxLayout(scale_row)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setAccessibleName(_("Photo Size"))
        self.scale_slider.setRange(10, 100)
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 100)
        self.scale_spin.setSuffix("%")
        scale_layout.addWidget(self.scale_slider)
        scale_layout.addWidget(self.scale_spin)
        size_presets, self.photo_size_preset_buttons = make_photo_size_preset_buttons(
            self._apply_photo_size_preset
        )
        frame_layout.addRow(_("Photo Size"), scale_row)
        frame_layout.addRow("", size_presets)
        self.x_spin = QDoubleSpinBox()
        self.y_spin = QDoubleSpinBox()
        for spin in (self.x_spin, self.y_spin):
            spin.setRange(-1.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
        self.x_spin.setAccessibleName(_("Horizontal position of selected photo"))
        self.y_spin.setAccessibleName(_("Vertical position of selected photo"))
        frame_layout.addRow(_("Horizontal"), self.x_spin)
        frame_layout.addRow(_("Vertical"), self.y_spin)
        self.reset_override_button = QPushButton(_("Reset Photo Framing"))
        self.reset_override_button.setToolTip(_("Restore this photo's size and position to the current frame defaults."))
        self.apply_all_button = QPushButton(_("Apply Framing to All"))
        self.apply_all_button.setToolTip(_("Use this photo's size and position for every photo, replacing individual adjustments."))
        self.save_frame_button = QPushButton(_("Save as Frame Preset"))
        frame_layout.addRow(self.reset_override_button)
        frame_layout.addRow(self.apply_all_button)
        frame_layout.addRow(self.save_frame_button)

        self.frame_scroll = QScrollArea()
        self.frame_scroll.setWidgetResizable(True)
        self.frame_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.frame_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frame_scroll.setMinimumWidth(290)
        self.frame_scroll.setWidget(self.frame_panel)

        splitter.addWidget(left)
        splitter.addWidget(self.preview_widget)
        splitter.addWidget(self.frame_scroll)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([256, 624, 300])
        root_layout.addWidget(splitter, 1)

        footer = QWidget()
        footer.setObjectName("footerBar")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bottom = QVBoxLayout(footer)
        bottom.setContentsMargins(16, 10, 16, 12)
        bottom.setSpacing(8)
        output_row = QHBoxLayout()
        output_row.setSpacing(10)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        self.output_folder_button = QPushButton(_("Output Folder"))
        self.output_folder_label = ElidedLabel(_("Output folder: Not selected — choose where framed photos go"))
        self.output_folder_label.setObjectName("mutedLabel")
        self.output_folder_label.setAccessibleName(_("Output folder"))
        self.result_summary_label = ElidedLabel()
        self.result_summary_label.setObjectName("mutedLabel")
        self.export_progress_bar = QProgressBar()
        self.export_progress_bar.setAccessibleName(_("Export progress"))
        self.export_progress_bar.setTextVisible(False)
        self.export_progress_bar.setMinimumWidth(120)
        self.export_progress_bar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.export_progress_bar.hide()
        # The one place the running file is named (the status bar stays quiet).
        self.export_progress_label = ElidedLabel()
        self.export_progress_label.hide()
        self.export_selected_button = QPushButton(_("Export Selected"))
        self.export_all_button = QPushButton(_("Export All"))
        self.export_all_button.setObjectName("primaryButton")
        self.cancel_button = QPushButton(_("Stop After This Photo"))
        self.cancel_button.setToolTip(_("Finish the photo being exported, then stop (Esc)"))
        self.cancel_button.hide()
        output_row.addWidget(self.output_folder_button)
        output_row.addWidget(self.output_folder_label, 1)
        actions_row.addWidget(self.result_summary_label, 1)
        actions_row.addWidget(self.export_progress_label, 1)
        actions_row.addWidget(self.export_progress_bar, 1)
        actions_row.addWidget(self.export_selected_button)
        actions_row.addWidget(self.export_all_button)
        actions_row.addWidget(self.cancel_button)
        bottom.addLayout(output_row)
        bottom.addLayout(actions_row)
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
        self.thumbnail_view.verticalScrollBar().valueChanged.connect(self._schedule_thumbnails)
        self.thumbnail_loader.thumbnailReady.connect(self._thumbnail_ready)
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
        self.controller.importStatus.connect(self._show_import_status)
        self.controller.busyChanged.connect(self._busy_changed)
        self.controller.exportProgress.connect(self._export_progress)
        self.controller.exportFinished.connect(self._export_finished)
        self.controller.importFailed.connect(self._retry_import_failed)
        self.controller.exportAborted.connect(self._retry_export_aborted)
        self.controller.shutdownFinished.connect(self._finish_close)

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
            if not self._select_combo(self.frame_preset_combo, self.controller.state.working_frame.id):
                if self.preset_store is not None:
                    self._select_combo(self.frame_preset_combo, self.preset_store.default_frame().id)
            if not self._select_combo(self.output_profile_combo, self.controller.state.output_profile.id):
                if self.preset_store is not None:
                    self._select_combo(self.output_profile_combo, self.preset_store.default_output().id)
        frame = self.frame_preset_combo.currentData()
        output = self.output_profile_combo.currentData()
        if frame is not None:
            self.controller.state.working_frame = frame
        if output is not None:
            self.controller.state.output_profile = output

    @staticmethod
    def _select_combo(combo: QComboBox, preset_id: str) -> bool:
        for index in range(combo.count()):
            preset = combo.itemData(index)
            if preset is not None and preset.id == preset_id:
                combo.setCurrentIndex(index)
                return True
        return False

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
        if self.preset_store is None:
            return
        dialog = PresetsManagerDialog(
            self.preset_store,
            self,
            current_frame=self._current_frame_with_edits(),
            current_output=self.controller.state.output_profile,
            on_use_frame=self._use_frame_preset,
            on_use_output=self._use_output_profile,
        )
        self._last_presets_dialog = dialog
        working = self.controller.state.working_frame
        stored_before = self._stored_frame()
        self._frame_chosen_in_manager = False
        if self._interactive_dialogs:
            dialog.exec()
        # Presets may have been created, renamed or deleted in there.
        self._reload_preset_combos()
        state = self.controller.state
        if (
            not self._frame_chosen_in_manager
            and working.id == state.working_frame.id
            and self._stored_frame() == stored_before
        ):
            # Nothing changed for this preset: keep the user's unsaved edits.
            state.working_frame = working
        self._sync_controls()
        self._request_selected_preview()

    def _stored_frame(self) -> FramePreset:
        """The preset the working frame came from (the combo keeps its stored copy)."""
        stored = self.frame_preset_combo.currentData()
        return stored if stored is not None else self.controller.state.working_frame

    def _current_frame_with_edits(self) -> FramePreset:
        """The working frame as edited now (ratio, background, border, offsets), not the saved copy."""
        return self.controller.state.working_frame

    def _use_frame_preset(self, preset: FramePreset) -> None:
        # An explicit "Use as current" must survive the manager closing.
        self._frame_chosen_in_manager = True
        self.controller.state.working_frame = preset
        self._reload_preset_combos()
        self._sync_controls()
        self._request_selected_preview()

    def _use_output_profile(self, profile: OutputProfile) -> None:
        self.controller.state.output_profile = profile
        self._reload_preset_combos()
        self._sync_controls()
        self._request_selected_preview()

    @Slot()
    def _save_frame_preset(self) -> None:
        current = replace(
            self.controller.state.working_frame,
            photo_scale=self.scale_spin.value() / 100.0,
            x=self.x_spin.value(),
            y=self.y_spin.value(),
        )
        self._edit_frame_preset(current, save_as=True)

    def _edit_frame_preset(self, preset: FramePreset | None = None, *, save_as: bool = False) -> None:
        dialog = FramePresetDialog(
            preset or self.controller.state.working_frame,
            self,
            store=self.preset_store,
            save_as=save_as,
        )
        if self._interactive_dialogs:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self.preset_store is not None:
                frames = {item.id: item for item in self.preset_store.list_frames()}
                saved = dialog.saved_preset
                chosen_id = saved.id if saved is not None else dialog.build_preset().id
                self.controller.state.working_frame = frames.get(chosen_id) or self.preset_store.default_frame()
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

    def queue_job_results(self, manifest: Path) -> None:
        """Open Job Results at one job. The Launcher's --retry lands here."""
        self._open_job_results(select=Path(manifest))

    @Slot()
    def _open_job_results(self, select: Path | None = None) -> QDialog | None:
        """Show what recent Frame exports wrote, skipped, or failed on."""
        from ndex_frame.ui.report_dialog import FrameJobReportDialog, frame_reports

        reports = frame_reports(select=select)
        if not reports:
            self.show_nonfatal_error(_("No export results recorded yet."))
            return None
        dialog = FrameJobReportDialog(reports, self, retry=self._retry_export, select=select)
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
            self.show_nonfatal_error(_("Wait for the running job to finish, then retry."))
            return
        paths = list(plan.paths)
        destination = Path(plan.report.destination) if plan.report.destination else None
        if destination is None or not destination.is_dir():
            self.show_nonfatal_error(
                _("That job's output folder is gone: {folder}").format(folder=plan.report.destination)
            )
            return
        if self._interactive_dialogs:
            answer = QMessageBox.question(
                self,
                _("Retry Failed"),
                plan.question(
                    destination_label=_("Output"), note=_("Frame opens just these files.")
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        # Remember the folder showing now: an abandoned retry puts it back.
        self._retry_previous_output = self.controller.state.output_directory
        self.controller.state.output_directory = destination
        self.sync_output_folder_label()
        self.pending_retry = plan

        loaded = {path_key(source.path): source for source in self.controller.state.sources}
        already_open = [loaded[key] for key in map(path_key, paths) if key in loaded]
        if len(already_open) == len(paths):
            self._export_retry(already_open)
            return

        # Some are not open. Load exactly those files; _sources_changed picks
        # the export up once the import lands.
        # Like every other import, this replaces the workspace, so a
        # handoff no longer describes it.
        self.handoff_path = None
        self._retry_importing = True
        self.controller.import_paths(paths)

    def _export_retry(self, sources: list[SourceItem]) -> None:
        try:
            self.confirm_export(sources, "rename")
        except Exception as error:
            self._drop_retry(_("Retry stopped: {reason}").format(reason=str(error) or error.__class__.__name__))

    def _drop_retry(self, message: str) -> None:
        """Forget a retry that cannot go ahead, and say so.

        Otherwise the flag would fire on the next unrelated import and the
        next export would be recorded as a retry of the wrong job. The
        output folder goes back to what it was: the retry changed it for
        pictures that are not going to be written.
        """
        self._retry_importing = False
        self.pending_retry = None
        self.controller.state.output_directory = self._retry_previous_output
        self._retry_previous_output = None
        self.sync_output_folder_label()
        self.show_nonfatal_error(message)

    @Slot(str)
    def _retry_import_failed(self, _message: str) -> None:
        if self._retry_importing:
            self._drop_retry(_("Retry stopped: the files could not be opened."))

    @Slot(str)
    def _retry_export_aborted(self, _message: str) -> None:
        # The export ended without a result, so nothing will record the
        # manifest that would have consumed the plan.
        if self.pending_retry is not None:
            self._drop_retry(_("Retry stopped: the export ended without a result."))

    @Slot()
    def _choose_files(self) -> None:
        names, _filter = QFileDialog.getOpenFileNames(self, _("Open Master Images"), "", _("Images (*.jpg *.jpeg *.png *.tif *.tiff)"))
        if names:
            self.handoff_path = None
            self.controller.import_paths([Path(name) for name in names])

    @Slot()
    def _choose_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, _("Open Master Folder"))
        if name:
            self.handoff_path = None
            self.controller.import_paths([Path(name)], origin=Path(name).name)

    @Slot(str)
    def _show_import_status(self, message: str) -> None:
        # Stays until the next thing worth saying: it is the answer to "what did I just open?".
        self.statusBar().showMessage(message)

    @Slot()
    def _choose_output_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, _("Select Output Folder"))
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
        if not self._retry_importing or self.pending_retry is None:
            return
        # Only the retry's own import may start the export. Anything else
        # arriving first (a drop, a handoff, Apply to all) means the
        # workspace is no longer what the retry was about.
        wanted = set(map(path_key, self.pending_retry.paths))
        loaded = {path_key(source.path) for source in self.controller.state.sources}
        self._retry_importing = False
        if loaded != wanted:
            self._drop_retry(_("Retry stopped: different files were opened."))
            return
        # Let the import finish emitting before the export claims the UI.
        QTimer.singleShot(0, self._start_pending_retry)

    def _start_pending_retry(self) -> None:
        if self.pending_retry is None:
            return
        self._export_retry(list(self.controller.state.sources))

    def _status_label(self, path: Path) -> str:
        return _(self._status_for(path))

    def _status_for(self, path: Path) -> str:
        export_status = self._source_export_status.get(path)
        if export_status in {"Error", "Exported", "Cancelled"}:
            return export_status
        if self.controller.state.is_modified(path):
            return "Modified"
        return "Default"

    @Slot()
    def _refresh_sources(self) -> None:
        selected = self.controller.state.selected_path
        self.images_label.setText(_("Images ({count})").format(count=len(self.controller.state.sources)))
        self._item_by_path = {}
        with QSignalBlocker(self.thumbnail_view):
            self.thumbnail_view.clear()
            for source in self.controller.state.sources:
                badge = "  ⚠" if source.warnings else ""
                item = QListWidgetItem(f"{source.path.name}\n{self._status_label(source.path)}{badge}")
                item.setToolTip(str(source.path))
                item.setData(Qt.ItemDataRole.UserRole, source.path)
                item.setIcon(self._icon_for(source.path))
                if source.warnings:
                    item.setToolTip("\n".join((source.path.name, *(f"⚠ {warning_text(text)}" for text in source.warnings))))
                self.thumbnail_view.addItem(item)
                self._item_by_path[source.path] = item
                if source.path == selected:
                    self.thumbnail_view.setCurrentItem(item)
        self._sync_controls()
        self._schedule_thumbnails()

    def _make_thumbnail_placeholder(self) -> QIcon:
        ratio = self.thumbnail_loader.ratio
        side = round(THUMBNAIL_SIZE * ratio)
        pixmap = QPixmap(side, side)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#E6E8EC"))
        painter.drawRoundedRect(pixmap.rect().adjusted(2, 2, -2, -2), 6 * ratio, 6 * ratio)
        painter.end()
        pixmap.setDevicePixelRatio(ratio)
        return QIcon(pixmap)

    def _icon_for(self, path: Path) -> QIcon:
        pixmap = self.thumbnail_loader.pixmap_for(path)
        return QIcon(pixmap) if pixmap is not None else self._thumbnail_placeholder

    @Slot()
    def _schedule_thumbnails(self, *_args: object) -> None:
        """Coalesce scroll/resize/refresh bursts into one request."""
        self._thumbnail_timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_thumbnails()

    def visible_thumbnail_paths(self, margin: int = 8) -> list[Path]:
        """Paths of the rows on screen, nearest the viewport first, plus ``margin`` rows each side."""
        view = self.thumbnail_view
        count = view.count()
        if count == 0:
            return []
        rect = view.viewport().rect()
        first = view.indexAt(rect.topLeft()).row()
        last = view.indexAt(QPoint(rect.left(), rect.bottom())).row()
        first = 0 if first < 0 else first
        last = count - 1 if last < 0 else last
        rows = list(range(first, last + 1))
        for offset in range(1, margin + 1):
            if last + offset < count:
                rows.append(last + offset)
            if first - offset >= 0:
                rows.append(first - offset)
        paths = []
        for row in rows:
            path = view.item(row).data(Qt.ItemDataRole.UserRole)
            if path is not None:
                paths.append(path)
        return paths

    @Slot()
    def load_visible_thumbnails(self) -> None:
        self.thumbnail_loader.request(self.visible_thumbnail_paths())

    @Slot(object)
    def _thumbnail_ready(self, path: Path) -> None:
        item = self._item_by_path.get(path)
        pixmap = self.thumbnail_loader.pixmap_for(path)
        if item is not None and pixmap is not None:
            item.setIcon(QIcon(pixmap))

    @Slot(object, object)
    def _thumbnail_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is not None:
            self.controller.select(current.data(Qt.ItemDataRole.UserRole))

    def _output_folder_ready(self) -> bool:
        directory = self.controller.state.output_directory
        return directory is not None and directory.is_dir()

    def _export_block_reason(self) -> str:
        """Why exporting is unavailable right now, or '' when it is available."""
        state = self.controller.state
        if self.controller._export_thread is not None:
            return _("An export is already running")
        if self._busy:
            return _("Wait for the photos to finish opening")
        if not state.sources:
            return _("Open photos first")
        if state.output_directory is None:
            return _("Choose an output folder first")
        if not state.output_directory.is_dir():
            return _("The output folder wasn't found — choose another one")
        return ""

    def _refresh_frame_preset_marker(self) -> None:
        """Mark the preset name '(edited)' once the working frame no longer matches it."""
        index = self.frame_preset_combo.currentIndex()
        preset = self.frame_preset_combo.currentData()
        if index < 0 or preset is None:
            return
        name = preset.name
        if self.controller.state.working_frame != preset:
            name = _("{name} (edited)").format(name=preset.name)
        if self.frame_preset_combo.itemText(index) != name:
            self.frame_preset_combo.setItemText(index, name)

    def _sync_controls(self) -> None:
        state = self.controller.state
        frame = state.working_frame
        self._update_output_folder_label()
        self._refresh_frame_preset_marker()
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
        exporting = self.controller._export_thread is not None
        # An import ending mid-export clears _busy; the export thread still
        # keeps the buttons off until the job itself is done.
        block_reason = self._export_block_reason()
        can_export = not block_reason
        for control in (
            self.open_files_button,
            self.open_folder_button,
            self.output_folder_button,
            self.frame_preset_combo,
            self.output_profile_combo,
            self.manage_presets_button,
            self.save_frame_button,
            self.ratio_width_spin,
            self.ratio_height_spin,
            self.custom_background_button,
            *self.ratio_preset_buttons,
            *self.background_preset_buttons,
        ):
            control.setEnabled(not exporting)
        has_selection = state.selected_path is not None and not exporting
        for control in (
            self.scale_slider, self.scale_spin, self.x_spin, self.y_spin,
            self.apply_all_button, *self.photo_size_preset_buttons,
        ):
            control.setEnabled(has_selection)
        self.reset_override_button.setEnabled(
            has_selection and state.is_modified(state.selected_path)
        )
        self.export_all_button.setEnabled(can_export)
        selected_ok = can_export and state.selected_path is not None
        self.export_selected_button.setEnabled(selected_ok)
        self.export_all_button.setToolTip(block_reason or _("Export every photo (Ctrl+E)"))
        self.export_selected_button.setToolTip(
            block_reason or (_("Export the selected photo (Ctrl+Shift+E)") if selected_ok else _("Select a photo first"))
        )
        has_override = state.selected_path is not None and state.is_modified(state.selected_path)
        self.reset_override_button.setEnabled(has_override and not exporting)
        self.reset_override_button.setToolTip(
            "" if has_override else _("This photo already uses the shared framing")
        )
        self.apply_all_button.setEnabled(bool(state.sources) and not exporting)
        self.apply_all_button.setToolTip("" if state.sources else _("Open photos first"))

    @Slot()
    def _reset_override(self) -> None:
        self.controller.reset_selected_override()
        self._refresh_sources()

    @Slot()
    def _apply_all(self) -> None:
        count = len(self.controller.state.sources)
        if self._interactive_dialogs and count > 1:
            text = _("Apply this framing to all {count} photos?").format(count=count)
            if self.controller.state.overrides:
                text += " " + _("Individual adjustments will be replaced.")
            answer = QMessageBox.question(
                self,
                _("Apply Framing to All"),
                text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
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
        chosen = QColorDialog.getColor(current, self, _("Frame background"))
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
        ratio = self.controller.state.working_frame.ratio
        self.preview_widget.set_preview(
            QPixmap.fromImage(image), plan, background, x, y, (ratio.width, ratio.height)
        )

    def queue_source(self, source: Path) -> None:
        self.handoff_path = None
        if source.is_dir():
            self.controller.import_paths([source], origin=source.name)
        else:
            self.show_nonfatal_error(_("Source folder does not exist: {path}").format(path=source))

    def queue_handoff(self, handoff: Path) -> None:
        from ndex_common.manifest import handoff_files, load_manifest

        path = Path(handoff)
        payload = load_manifest(path)
        if payload is None:
            self.handoff_path = None
            self.show_nonfatal_error(_("Could not read handoff: {path}").format(path=path))
            return
        files = handoff_files(payload)
        listed = [Path(str(raw)) for raw in payload.get("files") or ()]
        listed += [
            Path(str(entry["path"]))
            for entry in payload.get("items") or ()
            if isinstance(entry, dict) and entry.get("path")
        ]
        raw_count = len({str(item).casefold() for item in listed if item.suffix.casefold() in RAW_SUFFIXES})
        if not files:
            self.handoff_path = None
            if raw_count:
                self.show_nonfatal_error(
                    _("No photos opened from Image Manager · {count} skipped ({hint})").format(
                        count=ngettext("{count} RAW file", "{count} RAW files", raw_count).format(count=raw_count),
                        hint=raw_hint(),
                    )
                )
            else:
                self.show_nonfatal_error(_("Handoff has no JPG/PNG/TIFF files Frame can import."))
            return
        self.handoff_path = path
        self.controller.import_paths(files, origin="Image Manager", extra_raw=raw_count)

    @Slot(str)
    def show_nonfatal_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 10000)

    def _block_error(self, title: str, message: str) -> None:
        """An error that stops what the user just asked for: say it in a dialog, not only a status line."""
        self.statusBar().showMessage(message, 15000)
        if self._interactive_dialogs:
            QMessageBox.warning(self, title, message)

    def _export_request(
        self, sources: list[SourceItem] | None, collision_policy: str
    ) -> ExportRequest:
        selected = tuple(sources if sources is not None else self.controller.state.sources)
        directory = self.controller.state.output_directory
        if directory is None:
            raise ValueError(_("Output folder is unavailable."))
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
        if self.controller._export_thread is not None:
            raise RuntimeError(_("An export is already running. Wait for it to finish."))
        selected = list(sources) if sources is not None else list(self.controller.state.sources)
        plan_export(self._export_request(selected, collision_policy))
        self.last_export_result = None
        self._export_total = len(selected)
        self.export_progress_bar.setRange(0, max(1, len(selected)))
        self.export_progress_bar.setValue(0)
        self.export_progress_bar.setFormat(_("%v / %m"))
        self.export_progress_bar.show()
        self.export_progress_label.setText(_("Starting export of {count}…").format(count=len(selected)))
        self.export_progress_label.show()
        self.controller.start_export(selected, collision_policy)

    def _prompt_export(self, sources: list[SourceItem] | None) -> None:
        reason = self._export_block_reason()
        if reason:
            self.show_nonfatal_error(reason)
            return
        directory = self.controller.state.output_directory
        chosen = list(sources) if sources is not None else list(self.controller.state.sources)
        try:
            skip_request = self._export_request(sources, "skip")
            snapshot = plan_export(skip_request)
            rename_snapshot = plan_export(replace(skip_request, collision_policy="rename"))
        except Exception as error:
            self._block_error(_("Can't start the export"), describe_error(error, folder=directory))
            return
        counts = summarize_preflight(snapshot)
        info = describe_preflight(
            snapshot,
            rename_snapshot=rename_snapshot if counts.conflicted else None,
            notes=colour_notes(chosen),
        )
        dialog = ExportPreflightDialog(
            counts, has_conflicts=counts.conflicted > 0, parent=self, info=info
        )
        self._last_preflight_dialog = dialog
        if self._interactive_dialogs:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
        policy = dialog.collision_policy()
        if policy not in {"skip", "rename"}:
            return
        try:
            self.confirm_export(sources, policy)
        except Exception as error:
            self._block_error(_("Can't start the export"), describe_error(error, folder=directory))

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
            self.export_progress_label.show()
        else:
            self.export_progress_bar.hide()
            self.export_progress_label.hide()
        if not exporting:
            self.cancel_button.setText(_("Stop After This Photo"))
        self._sync_controls()

    @Slot(object)
    def _export_progress(self, progress: object) -> None:
        total = max(1, int(getattr(progress, "total", 1) or 1))
        index = max(0, min(total, int(getattr(progress, "index", 0) or 0)))
        name = getattr(getattr(progress, "source", None), "name", "")
        self.export_progress_bar.setRange(0, total)
        self.export_progress_bar.setValue(index)
        self.export_progress_bar.setToolTip(name)
        self.export_progress_bar.show()
        text = _("Exporting {index} of {total}").format(index=index, total=total)
        self.export_progress_label.setText(f"{text} — {name}" if name else text)
        self.export_progress_label.setToolTip(self.export_progress_label.text())
        self.export_progress_label.show()

    @Slot(object)
    def _export_finished(self, result: object) -> None:
        self.last_export_result = result  # type: ignore[assignment]
        self.cancel_button.hide()
        self.cancel_button.setText(_("Stop After This Photo"))
        self.export_progress_bar.hide()
        self.export_progress_bar.reset()
        self.export_progress_label.hide()
        self.export_progress_label.clear()
        for item in getattr(result, "items", ()):
            if item.state == "exported":
                self._source_export_status[item.source] = "Exported"
            elif item.state == "failed":
                self._source_export_status[item.source] = (
                    "Cancelled" if item.message == "not run: cancelled" else "Error"
                )
        cancelled = 0
        if getattr(result, "cancelled", False):
            cancelled = getattr(result, "cancelled_count", 0) or max(
                0,
                self._export_total - result.exported - result.skipped - result.failed,
            )
        output_dir = getattr(result, "output_dir", None) or self.controller.state.output_directory
        dialog = ExportCompletionDialog(
            result,
            cancelled,
            output_dir,
            self,
            on_view_results=lambda: QTimer.singleShot(0, self._open_job_results),
            view_results_available=self._job_results_available(),
        )
        self._last_completion_dialog = dialog
        self.statusBar().showMessage(completion_title(result, cancelled), 15000)
        self._refresh_sources()
        if self._interactive_dialogs:
            # The job is written to Job Results after this handler returns, so
            # showing the dialog a beat later lets "View in Job Results" find it.
            QTimer.singleShot(0, lambda: self._show_completion(dialog))

    @staticmethod
    def _job_results_available() -> bool:
        from ndex_frame.ui.report_dialog import frame_reports

        try:
            return bool(frame_reports(limit=1))
        except Exception:
            return False

    def _show_completion(self, dialog: ExportCompletionDialog) -> None:
        if not self._interactive_dialogs:
            return
        dialog.set_job_results_available(self._job_results_available())
        dialog.exec()
