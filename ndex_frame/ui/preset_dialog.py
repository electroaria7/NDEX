"""Frame Preset editor, preflight collision choice, and export completion UI."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ndex_frame.core.framing_choices import normalize_hex_color
from ndex_frame.core.models import AspectRatio, FramePreset
from ndex_frame.services.export_job import ExportJobSnapshot, ExportResult
from ndex_frame.services.presets import PresetStore
from ndex_frame.ui.framing_widgets import make_background_preset_buttons, make_photo_size_preset_buttons
from ndex_frame.ui.profile_dialog import custom_preset_id, store_preset_ids


@dataclass(frozen=True, slots=True)
class PreflightCounts:
    exportable: int
    skipped: int
    conflicted: int
    invalid: int


def summarize_preflight(snapshot: ExportJobSnapshot) -> PreflightCounts:
    exportable = conflicted = invalid = 0
    for item in snapshot.items:
        if item.action == "error":
            invalid += 1
        elif item.action == "skip":
            conflicted += 1
        else:
            exportable += 1
    return PreflightCounts(exportable, 0, conflicted, invalid)


class FramePresetDialog(QDialog):
    def __init__(
        self,
        preset: FramePreset,
        parent: QWidget | None = None,
        *,
        store: PresetStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._preset = preset
        self._store = store
        self.setWindowTitle("Frame Preset")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(preset.name)
        self.ratio_width_spin = QSpinBox()
        self.ratio_height_spin = QSpinBox()
        for spin in (self.ratio_width_spin, self.ratio_height_spin):
            spin.setRange(1, 99)
        self.ratio_width_spin.setValue(preset.ratio.width)
        self.ratio_height_spin.setValue(preset.ratio.height)
        self.background_edit = QLineEdit(preset.background)
        background_presets, self.background_preset_buttons, self.custom_background_button = (
            make_background_preset_buttons(self._apply_background, self._pick_background)
        )
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 100)
        self.scale_spin.setSuffix("%")
        self.scale_spin.setValue(round(preset.photo_scale * 100))
        size_presets, self.photo_size_preset_buttons = make_photo_size_preset_buttons(
            self.scale_spin.setValue
        )
        self.x_spin = QDoubleSpinBox()
        self.y_spin = QDoubleSpinBox()
        for spin in (self.x_spin, self.y_spin):
            spin.setRange(-1.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
        self.x_spin.setValue(preset.x)
        self.y_spin.setValue(preset.y)
        form.addRow("Name", self.name_edit)
        form.addRow("Ratio width", self.ratio_width_spin)
        form.addRow("Ratio height", self.ratio_height_spin)
        form.addRow("Background", self.background_edit)
        form.addRow("", background_presets)
        form.addRow("Photo Size", self.scale_spin)
        form.addRow("", size_presets)
        form.addRow("X", self.x_spin)
        form.addRow("Y", self.y_spin)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.duplicate_button = QPushButton("Duplicate as Custom Preset")
        self.save_button = QPushButton("Save")
        self.save_as_button = QPushButton("Save As")
        self.delete_button = QPushButton("Delete")
        self.set_default_button = QPushButton("Set as Default")
        for button in (
            self.duplicate_button,
            self.save_button,
            self.save_as_button,
            self.delete_button,
            self.set_default_button,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.duplicate_button.clicked.connect(self._duplicate)
        self.save_button.clicked.connect(lambda: self._save(save_as=False))
        self.save_as_button.clicked.connect(lambda: self._save(save_as=True))
        self.delete_button.clicked.connect(self._delete)
        self.set_default_button.clicked.connect(self.set_as_default)
        self._refresh_action_buttons()

    def _apply_background(self, color: str) -> None:
        normalized = normalize_hex_color(color)
        if normalized is not None:
            self.background_edit.setText(normalized)

    def _pick_background(self) -> None:
        current = QColor(self.background_edit.text() or self._preset.background)
        chosen = QColorDialog.getColor(current, self, "Frame background")
        if chosen.isValid():
            self._apply_background(chosen.name())

    def _refresh_action_buttons(self) -> None:
        builtin = self._preset.builtin
        self.duplicate_button.setVisible(builtin)
        self.save_button.setVisible(not builtin)
        self.save_as_button.setVisible(not builtin)
        self.delete_button.setVisible(not builtin)

    def build_preset(self, *, save_as: bool = False) -> FramePreset:
        name = self.name_edit.text().strip() or self._preset.name
        if self._preset.builtin or save_as:
            preset_id = custom_preset_id(name, store_preset_ids(self._store))
        else:
            preset_id = self._preset.id
        color = normalize_hex_color(self.background_edit.text()) or self._preset.background
        return FramePreset(
            preset_id,
            name,
            self._preset.version,
            AspectRatio(self.ratio_width_spin.value(), self.ratio_height_spin.value()),
            color,
            self.scale_spin.value() / 100.0,
            self.x_spin.value(),
            self.y_spin.value(),
            False,
        )

    def set_as_default(self) -> None:
        if self._store is None:
            return
        self._store.set_default_frame(self._preset.id)

    def _persist(self, preset: FramePreset) -> None:
        if self._store is not None:
            self._store.save_frame(preset)
        self._preset = preset
        self._refresh_action_buttons()

    def _duplicate(self) -> None:
        self._persist(self.build_preset(save_as=True))
        self.accept()

    def _save(self, *, save_as: bool) -> None:
        self._persist(self.build_preset(save_as=save_as))
        self.accept()

    def _delete(self) -> None:
        if self._store is None or self._preset.builtin:
            return
        self._store.delete_custom(self._preset.id, kind="frame")
        self.accept()


class ExportPreflightDialog(QDialog):
    def __init__(
        self,
        counts: PreflightCounts,
        *,
        has_conflicts: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._counts = counts
        self.setWindowTitle("Export Preflight")
        layout = QVBoxLayout(self)
        self.exportable_label = QLabel(f"Exportable: {counts.exportable}")
        self.skipped_label = QLabel(f"Skipped: {counts.skipped}")
        self.conflicted_label = QLabel(f"Conflicted: {counts.conflicted}")
        self.invalid_label = QLabel(f"Invalid: {counts.invalid}")
        for label in (
            self.exportable_label,
            self.skipped_label,
            self.conflicted_label,
            self.invalid_label,
        ):
            layout.addWidget(label)

        self.skip_radio = QRadioButton("Skip existing")
        self.rename_radio = QRadioButton("Auto rename")
        self._policy_group = QButtonGroup(self)
        self._policy_group.setExclusive(True)
        self._policy_group.addButton(self.skip_radio)
        self._policy_group.addButton(self.rename_radio)
        if has_conflicts:
            layout.addWidget(QLabel("Choose how to handle existing files:"))
            layout.addWidget(self.skip_radio)
            layout.addWidget(self.rename_radio)
        else:
            self.rename_radio.setChecked(True)
            self.skip_radio.hide()
            self.rename_radio.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.export_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.export_button.setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.skip_radio.toggled.connect(self._refresh_export_enabled)
        self.rename_radio.toggled.connect(self._refresh_export_enabled)
        self._refresh_export_enabled()

    def collision_policy(self) -> str | None:
        if self.skip_radio.isChecked():
            return "skip"
        if self.rename_radio.isChecked():
            return "rename"
        return None

    def _refresh_export_enabled(self) -> None:
        policy = self.collision_policy()
        if policy is None:
            self.export_button.setEnabled(False)
            return
        exportable = self._counts.exportable
        if policy == "rename":
            exportable += self._counts.conflicted
        self.export_button.setEnabled(exportable > 0)


class ExportCompletionDialog(QDialog):
    def __init__(
        self,
        result: ExportResult,
        cancelled_count: int,
        output_directory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._output_directory = output_directory
        self.setWindowTitle("Export Complete")
        layout = QVBoxLayout(self)
        self.summary_label = QLabel(
            f"Exported {result.exported} · Skipped {result.skipped} · Failed {result.failed} · Cancelled {cancelled_count}"
        )
        layout.addWidget(self.summary_label)
        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_folder_button.clicked.connect(self.open_output_folder)
        layout.addWidget(self.open_folder_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def open_output_folder(self) -> None:
        if self._output_directory is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_directory)))


class ManagePresetsDialog(QDialog):
    """Small chooser so Manage Presets can open the Frame or Output editor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.choice: str | None = None
        self.setWindowTitle("Manage Presets")
        layout = QVBoxLayout(self)
        self.edit_frame_button = QPushButton("Edit Frame Preset")
        self.edit_output_button = QPushButton("Edit Output Profile")
        self.edit_frame_button.clicked.connect(lambda: self._choose("frame"))
        self.edit_output_button.clicked.connect(lambda: self._choose("output"))
        layout.addWidget(self.edit_frame_button)
        layout.addWidget(self.edit_output_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose(self, kind: str) -> None:
        self.choice = kind
        self.accept()
