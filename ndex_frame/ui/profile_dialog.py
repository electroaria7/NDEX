"""Output Profile editor with basic format/sizing and Advanced quality settings."""

from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ndex_frame.core.geometry import resolve_canvas
from ndex_frame.core.models import AspectRatio, MetadataPolicy, OutputProfile, OutputSizing
from ndex_frame.services.presets import PresetStore

_UNSAFE = re.compile(r"[^A-Za-z0-9]+")
_FORMATS = ("jpeg", "png", "webp")
_CHROMA = ("4:4:4", "4:2:2", "4:2:0")
_SIZING_MODES = (
    ("fixed_width", "Fixed width"),
    ("fixed_height", "Fixed height"),
    ("long_edge", "Long edge"),
    ("fixed_dimensions", "Fixed dimensions"),
)


def custom_preset_id(name: str) -> str:
    slug = _UNSAFE.sub("-", name).strip("-").lower() or "preset"
    if slug[0] in ".-":
        slug = f"p{slug}"
    return f"custom.{slug}"


class OutputProfileDialog(QDialog):
    def __init__(
        self,
        profile: OutputProfile,
        ratio: AspectRatio,
        parent: QWidget | None = None,
        *,
        store: PresetStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._ratio = ratio
        self._store = store
        self.setWindowTitle("Output Profile")
        self._build_widgets()
        self._apply_profile(profile)
        self._refresh_action_buttons()

    def _build_widgets(self) -> None:
        layout = QVBoxLayout(self)
        self.basic_group = QGroupBox("Basic")
        basic = QFormLayout(self.basic_group)
        self.name_edit = QLineEdit()
        self.format_combo = QComboBox()
        for image_format in _FORMATS:
            self.format_combo.addItem(image_format.upper(), image_format)
        self.sizing_mode_combo = QComboBox()
        for mode, label in _SIZING_MODES:
            self.sizing_mode_combo.addItem(label, mode)
        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        self.long_edge_spin = QSpinBox()
        for spin in (self.width_spin, self.height_spin, self.long_edge_spin):
            spin.setRange(1, 20000)
        self.computed_size_label = QLabel()
        basic.addRow("Name", self.name_edit)
        basic.addRow("Format", self.format_combo)
        basic.addRow("Sizing", self.sizing_mode_combo)
        basic.addRow("Width", self.width_spin)
        basic.addRow("Height", self.height_spin)
        basic.addRow("Long edge", self.long_edge_spin)
        basic.addRow("Computed size", self.computed_size_label)

        self.advanced_group = QGroupBox("Advanced")
        advanced = QFormLayout(self.advanced_group)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.chroma_combo = QComboBox()
        for chroma in _CHROMA:
            self.chroma_combo.addItem(chroma, chroma)
        self.color_space_combo = QComboBox()
        self.color_space_combo.addItem("sRGB", "sRGB")
        self.embed_icc_checkbox = QCheckBox("Embed ICC")
        self.preserve_capture_checkbox = QCheckBox("Preserve capture metadata")
        self.preserve_copyright_checkbox = QCheckBox("Preserve copyright")
        self.remove_gps_checkbox = QCheckBox("Remove GPS")
        advanced.addRow("Quality", self.quality_spin)
        advanced.addRow("Chroma", self.chroma_combo)
        advanced.addRow("Color space", self.color_space_combo)
        advanced.addRow(self.embed_icc_checkbox)
        advanced.addRow(self.preserve_capture_checkbox)
        advanced.addRow(self.preserve_copyright_checkbox)
        advanced.addRow(self.remove_gps_checkbox)

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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout.addWidget(self.basic_group)
        layout.addWidget(self.advanced_group)
        layout.addLayout(actions)
        layout.addWidget(buttons)

        self.sizing_mode_combo.currentIndexChanged.connect(self._sizing_mode_changed)
        self.width_spin.valueChanged.connect(self._refresh_computed_size)
        self.height_spin.valueChanged.connect(self._refresh_computed_size)
        self.long_edge_spin.valueChanged.connect(self._refresh_computed_size)
        self.duplicate_button.clicked.connect(self._duplicate)
        self.save_button.clicked.connect(lambda: self._save(save_as=False))
        self.save_as_button.clicked.connect(lambda: self._save(save_as=True))
        self.delete_button.clicked.connect(self._delete)
        self.set_default_button.clicked.connect(self.set_as_default)

    def _apply_profile(self, profile: OutputProfile) -> None:
        self._profile = profile
        self.name_edit.setText(profile.name)
        self._set_combo(self.format_combo, profile.format)
        self._set_combo(self.sizing_mode_combo, profile.sizing.mode)
        self.width_spin.setValue(profile.sizing.width or profile.sizing.long_edge or 1080)
        self.height_spin.setValue(profile.sizing.height or 1440)
        self.long_edge_spin.setValue(profile.sizing.long_edge or profile.sizing.width or 1080)
        self.quality_spin.setValue(profile.quality)
        self._set_combo(self.chroma_combo, profile.chroma_subsampling)
        self._set_combo(self.color_space_combo, profile.color_space)
        self.embed_icc_checkbox.setChecked(profile.embed_icc)
        self.preserve_capture_checkbox.setChecked(profile.metadata.preserve_capture)
        self.preserve_copyright_checkbox.setChecked(profile.metadata.preserve_copyright)
        self.remove_gps_checkbox.setChecked(profile.metadata.remove_gps)
        self._sizing_mode_changed()
        self._refresh_action_buttons()

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _sizing_mode_changed(self) -> None:
        mode = self.sizing_mode_combo.currentData()
        self.width_spin.setEnabled(mode in {"fixed_width", "fixed_dimensions"})
        self.height_spin.setEnabled(mode in {"fixed_height", "fixed_dimensions"})
        self.long_edge_spin.setEnabled(mode == "long_edge")
        self._refresh_computed_size()

    def _refresh_computed_size(self) -> None:
        try:
            width, height = resolve_canvas(self._current_sizing(), self._ratio)
            self.computed_size_label.setText(f"{width} × {height}")
        except (TypeError, ValueError):
            self.computed_size_label.setText("Invalid size")

    def _current_sizing(self) -> OutputSizing:
        mode = self.sizing_mode_combo.currentData()
        return OutputSizing(
            mode,
            width=self.width_spin.value() if mode in {"fixed_width", "fixed_dimensions"} else None,
            height=self.height_spin.value() if mode in {"fixed_height", "fixed_dimensions"} else None,
            long_edge=self.long_edge_spin.value() if mode == "long_edge" else None,
        )

    def _refresh_action_buttons(self) -> None:
        builtin = self._profile.builtin
        self.duplicate_button.setVisible(builtin)
        self.save_button.setVisible(not builtin)
        self.save_as_button.setVisible(not builtin)
        self.delete_button.setVisible(not builtin)

    def build_profile(self, *, save_as: bool = False) -> OutputProfile:
        name = self.name_edit.text().strip() or self._profile.name
        builtin = False
        if self._profile.builtin or save_as:
            profile_id = custom_preset_id(name)
        else:
            profile_id = self._profile.id
        return OutputProfile(
            profile_id,
            name,
            self._profile.version,
            self._current_sizing(),
            self.format_combo.currentData(),
            self.quality_spin.value(),
            self.chroma_combo.currentData(),
            self.color_space_combo.currentData(),
            self.embed_icc_checkbox.isChecked(),
            MetadataPolicy(
                self.preserve_capture_checkbox.isChecked(),
                self.preserve_copyright_checkbox.isChecked(),
                self.remove_gps_checkbox.isChecked(),
            ),
            builtin,
        )

    def set_as_default(self) -> None:
        if self._store is None:
            return
        self._store.set_default_output(self._profile.id)

    def _persist(self, profile: OutputProfile) -> None:
        if self._store is not None:
            self._store.save_output(profile)
        self._apply_profile(profile)

    def _duplicate(self) -> None:
        self._persist(self.build_profile(save_as=True))
        self.accept()

    def _save(self, *, save_as: bool) -> None:
        self._persist(self.build_profile(save_as=save_as))
        self.accept()

    def _delete(self) -> None:
        if self._store is None or self._profile.builtin:
            return
        self._store.delete_custom(self._profile.id, kind="output")
        self.accept()
