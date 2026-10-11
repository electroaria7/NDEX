"""One window for every Frame preset and Output profile.

Two lists side by side, each with New / Duplicate / Edit / Rename / Delete and a
live summary of the selected item. Built-in items are read-only (Duplicate only).
Editing still goes through the existing Frame Preset and Output Profile dialogs;
the store format is untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ndex_common.i18n import _
from ndex_frame.core.models import FramePreset, OutputProfile
from ndex_frame.services.presets import PresetStore
from ndex_frame.ui.preset_dialog import FramePresetDialog, metadata_summary
from ndex_frame.ui.profile_dialog import OutputProfileDialog, custom_preset_id, store_preset_ids

FRAME = "frame"
OUTPUT = "output"


class PresetNameError(ValueError):
    """The requested name is empty or already used by another preset of the same kind."""


def frame_summary(preset: FramePreset) -> str:
    """Ratio, background and border of a frame, one per line."""
    border = max(0, round((1.0 - preset.photo_scale) * 100))
    if border:
        border_text = _("{border}% (photo fills {fill}%)").format(
            border=border, fill=round(preset.photo_scale * 100)
        )
    else:
        border_text = _("None (photo fills the frame)")
    return "\n".join(
        (
            _("Ratio: {width}:{height}").format(width=preset.ratio.width, height=preset.ratio.height),
            _("Background: {color}").format(color=preset.background),
            _("Border: {border}").format(border=border_text),
        )
    )


def _sizing_text(profile: OutputProfile) -> str:
    sizing = profile.sizing
    if sizing.mode == "fixed_width":
        return _("{value} px wide").format(value=sizing.width)
    if sizing.mode == "fixed_height":
        return _("{value} px tall").format(value=sizing.height)
    if sizing.mode == "long_edge":
        return _("{value} px on the long edge").format(value=sizing.long_edge)
    return _("{width} × {height} px").format(width=sizing.width, height=sizing.height)


def output_summary(profile: OutputProfile) -> str:
    """Size, format, quality and metadata of an output profile, one per line."""
    format_text = profile.format.upper()
    if profile.format != "png":
        format_text = _("{format} · quality {quality}").format(format=format_text, quality=profile.quality)
    return "\n".join(
        (
            _("Size: {size}").format(size=_sizing_text(profile)),
            _("Format: {format}").format(format=format_text),
            _("Metadata: {metadata}").format(metadata=metadata_summary(profile.metadata)),
        )
    )


class _Column(QGroupBox):
    """One list with its summary and buttons."""

    def __init__(self, kind: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.kind = kind
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setAccessibleName(title)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setMinimumHeight(150)
        layout.addWidget(self.list, 1)
        self.summary = QLabel()
        self.summary.setObjectName("mutedLabel")
        self.summary.setWordWrap(True)
        self.summary.setAccessibleName(_("Selected preset summary"))
        self.summary.setMinimumHeight(64)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.summary)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.new_button = QPushButton(_("New"))
        self.duplicate_button = QPushButton(_("Duplicate"))
        self.edit_button = QPushButton(_("Edit…"))
        self.rename_button = QPushButton(_("Rename…"))
        self.delete_button = QPushButton(_("Delete"))
        self.default_button = QPushButton(_("Make Default"))
        for index, button in enumerate(
            (
                self.new_button,
                self.duplicate_button,
                self.edit_button,
                self.rename_button,
                self.delete_button,
                self.default_button,
            )
        ):
            grid.addWidget(button, index // 3, index % 3)
        layout.addLayout(grid)
        self.use_button = QPushButton(_("Use as Current Frame") if kind == FRAME else _("Use as Current Output"))
        self.use_button.setObjectName("primaryButton")
        layout.addWidget(self.use_button)

    def selected_id(self) -> str | None:
        item = self.list.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)


class PresetsManagerDialog(QDialog):
    def __init__(
        self,
        store: PresetStore,
        parent: QWidget | None = None,
        *,
        current_frame: FramePreset,
        current_output: OutputProfile,
        on_use_frame: Callable[[FramePreset], None] | None = None,
        on_use_output: Callable[[OutputProfile], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.current_frame = current_frame
        self.current_output = current_output
        self._on_use = {FRAME: on_use_frame, OUTPUT: on_use_output}
        self.setWindowTitle(_("Manage Presets"))
        self.setMinimumSize(660, 440)
        self.resize(780, 500)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.frames = _Column(FRAME, _("Frames"))
        self.outputs = _Column(OUTPUT, _("Outputs"))
        row.addWidget(self.frames, 1)
        row.addWidget(self.outputs, 1)
        layout.addLayout(row, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for column in (self.frames, self.outputs):
            column.list.currentItemChanged.connect(lambda *_a, c=column: self._selection_changed(c))
            column.list.itemDoubleClicked.connect(lambda _item, c=column: self.use(c.kind))
            column.new_button.clicked.connect(lambda _c=False, c=column: self._prompt_new(c.kind))
            column.duplicate_button.clicked.connect(lambda _c=False, c=column: self._duplicate_selected(c.kind))
            column.edit_button.clicked.connect(lambda _c=False, c=column: self._edit_selected(c.kind))
            column.rename_button.clicked.connect(lambda _c=False, c=column: self._prompt_rename(c.kind))
            column.delete_button.clicked.connect(lambda _c=False, c=column: self._confirm_delete(c.kind))
            column.default_button.clicked.connect(lambda _c=False, c=column: self.make_default(c.kind))
            column.use_button.clicked.connect(lambda _c=False, c=column: self.use(c.kind))
        self.reload()

    # ------------------------------------------------------------- data

    def column(self, kind: str) -> _Column:
        return self.frames if kind == FRAME else self.outputs

    def presets(self, kind: str):
        return self.store.list_frames() if kind == FRAME else self.store.list_outputs()

    def preset(self, kind: str, preset_id: str):
        return next((item for item in self.presets(kind) if item.id == preset_id), None)

    def selected(self, kind: str):
        preset_id = self.column(kind).selected_id()
        return None if preset_id is None else self.preset(kind, preset_id)

    def select(self, kind: str, preset_id: str) -> None:
        column = self.column(kind)
        for row in range(column.list.count()):
            if column.list.item(row).data(Qt.ItemDataRole.UserRole) == preset_id:
                column.list.setCurrentRow(row)
                return

    def reload(self, *, select_frame: str | None = None, select_output: str | None = None) -> None:
        """Refill both lists from the store, keeping (or moving) the selection."""
        wanted = {
            FRAME: select_frame or self.frames.selected_id() or self.current_frame.id,
            OUTPUT: select_output or self.outputs.selected_id() or self.current_output.id,
        }
        for kind in (FRAME, OUTPUT):
            column = self.column(kind)
            default_id = (self.store.default_frame() if kind == FRAME else self.store.default_output()).id
            current_id = (self.current_frame if kind == FRAME else self.current_output).id
            column.list.blockSignals(True)
            column.list.clear()
            for preset in self.presets(kind):
                tags = []
                if preset.builtin:
                    tags.append(_("built-in"))
                if preset.id == default_id:
                    tags.append(_("default"))
                if preset.id == current_id:
                    tags.append(_("in use"))
                text = f"{preset.name}  ({', '.join(tags)})" if tags else preset.name
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, preset.id)
                item.setToolTip(preset.name)
                column.list.addItem(item)
            column.list.blockSignals(False)
            self.select(kind, wanted[kind])
            if column.list.currentItem() is None and column.list.count():
                column.list.setCurrentRow(0)
            self._selection_changed(column)

    def _selection_changed(self, column: _Column) -> None:
        preset = self.selected(column.kind)
        has = preset is not None
        custom = has and not preset.builtin
        column.duplicate_button.setEnabled(has)
        column.use_button.setEnabled(has)
        column.default_button.setEnabled(has)
        for button in (column.edit_button, column.rename_button, column.delete_button):
            button.setEnabled(custom)
        tip = "" if custom else _("Built-in presets can't be changed. Duplicate one to make your own.")
        for button in (column.edit_button, column.rename_button, column.delete_button):
            button.setToolTip(tip)
        if preset is None:
            column.summary.setText("")
        elif column.kind == FRAME:
            column.summary.setText(frame_summary(preset))
        else:
            column.summary.setText(output_summary(preset))

    # ------------------------------------------------------------ operations

    def _unique_name(self, kind: str, base: str) -> str:
        taken = {item.name.casefold() for item in self.presets(kind)}
        name, number = base, 2
        while name.casefold() in taken:
            name = f"{base} {number}"
            number += 1
        return name

    def _checked_name(self, kind: str, name: str, *, ignore_id: str | None = None) -> str:
        name = " ".join(name.split())
        if not name:
            raise PresetNameError(_("Enter a name for the preset."))
        taken = {item.name.casefold() for item in self.presets(kind) if item.id != ignore_id}
        if name.casefold() in taken:
            raise PresetNameError(_("A preset named \"{name}\" already exists.").format(name=name))
        return name

    def _save(self, kind: str, preset) -> None:
        if kind == FRAME:
            self.store.save_frame(preset)
        else:
            self.store.save_output(preset)

    def _new_id(self, name: str) -> str:
        return custom_preset_id(name, store_preset_ids(self.store))

    def create(self, kind: str, name: str):
        """A new custom preset named ``name``, copying the current settings of that kind."""
        name = self._checked_name(kind, name)
        base = self.current_frame if kind == FRAME else self.current_output
        preset = replace(base, id=self._new_id(name), name=name, builtin=False)
        self._save(kind, preset)
        self.reload(**{f"select_{kind}": preset.id})
        return preset

    def duplicate(self, kind: str, preset_id: str):
        source = self.preset(kind, preset_id)
        if source is None:
            raise KeyError(preset_id)
        name = self._unique_name(kind, _("{name} copy").format(name=source.name))
        copy = replace(source, id=self._new_id(name), name=name, builtin=False)
        self._save(kind, copy)
        self.reload(**{f"select_{kind}": copy.id})
        return copy

    def rename(self, kind: str, preset_id: str, name: str):
        source = self.preset(kind, preset_id)
        if source is None or source.builtin:
            raise ValueError(_("Built-in presets can't be changed. Duplicate one to make your own."))
        name = self._checked_name(kind, name, ignore_id=preset_id)
        renamed = replace(source, name=name)
        self._save(kind, renamed)
        self.reload(**{f"select_{kind}": preset_id})
        return renamed

    def delete(self, kind: str, preset_id: str) -> None:
        source = self.preset(kind, preset_id)
        if source is None or source.builtin:
            raise ValueError(_("Built-in presets can't be changed. Duplicate one to make your own."))
        row = self.column(kind).list.currentRow()
        self.store.delete_custom(preset_id, kind=kind)
        self.reload()
        column = self.column(kind)
        if column.list.count():
            column.list.setCurrentRow(min(row, column.list.count() - 1))

    def make_default(self, kind: str) -> None:
        preset = self.selected(kind)
        if preset is None:
            return
        if kind == FRAME:
            self.store.set_default_frame(preset.id)
        else:
            self.store.set_default_output(preset.id)
        self.reload()

    def use(self, kind: str) -> None:
        """Make the selected preset current in the main window."""
        preset = self.selected(kind)
        if preset is None:
            return
        if kind == FRAME:
            self.current_frame = preset
        else:
            self.current_output = preset
        callback = self._on_use[kind]
        if callback is not None:
            callback(preset)
        self.reload()

    # ------------------------------------------------------------ prompts

    def _warn(self, error: Exception) -> None:
        QMessageBox.warning(self, self.windowTitle(), str(error))

    def _title(self, kind: str) -> str:
        return _("Frame preset") if kind == FRAME else _("Output profile")

    def _prompt_new(self, kind: str) -> None:
        suggestion = self._unique_name(kind, _("New frame preset") if kind == FRAME else _("New output profile"))
        name, accepted = QInputDialog.getText(self, self._title(kind), _("Name:"), text=suggestion)
        if accepted:
            try:
                self.create(kind, name)
            except PresetNameError as error:
                self._warn(error)

    def _duplicate_selected(self, kind: str) -> None:
        preset_id = self.column(kind).selected_id()
        if preset_id is not None:
            self.duplicate(kind, preset_id)

    def _prompt_rename(self, kind: str) -> None:
        preset = self.selected(kind)
        if preset is None or preset.builtin:
            return
        name, accepted = QInputDialog.getText(self, _("Rename"), _("Name:"), text=preset.name)
        if accepted:
            try:
                self.rename(kind, preset.id, name)
            except PresetNameError as error:
                self._warn(error)

    def _confirm_delete(self, kind: str) -> None:
        preset = self.selected(kind)
        if preset is None or preset.builtin:
            return
        answer = QMessageBox.question(
            self,
            _("Delete"),
            _("Delete \"{name}\"? This can't be undone.").format(name=preset.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete(kind, preset.id)

    def _edit_selected(self, kind: str) -> None:
        preset = self.selected(kind)
        if preset is None or preset.builtin:
            return
        if kind == FRAME:
            dialog = FramePresetDialog(preset, self, store=self.store)
        else:
            dialog = OutputProfileDialog(preset, self.current_frame.ratio, self, store=self.store)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        # Each dialog tracks the preset it last wrote (a Save As makes a new id).
        saved = dialog.saved_preset if kind == FRAME else dialog._profile
        self.reload(**{f"select_{kind}": saved.id if saved is not None else preset.id})

