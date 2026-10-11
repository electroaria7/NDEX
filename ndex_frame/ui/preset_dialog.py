"""Frame Preset editor, preflight collision choice, and export completion UI."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
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
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ndex_common.i18n import _, ngettext
from ndex_frame.core.framing_choices import normalize_hex_color
from ndex_frame.core.messages import clean_text
from ndex_frame.core.models import AspectRatio, FramePreset, MetadataPolicy, SourceItem
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


def metadata_summary(policy: MetadataPolicy) -> str:
    """One line for what the output keeps of the original's metadata."""
    parts = [
        _("capture info kept") if policy.preserve_capture else _("capture info removed"),
        _("copyright kept") if policy.preserve_copyright else _("copyright removed"),
        _("GPS location removed") if policy.remove_gps else _("GPS location kept"),
    ]
    text = " · ".join(parts)
    return text[0].upper() + text[1:]


def colour_notes(sources: Sequence[SourceItem]) -> tuple[str, ...]:
    """Preflight lines for photos whose colour handling the user should know about."""
    from ndex_frame.core.messages import NO_PROFILE_WARNING

    missing = sum(NO_PROFILE_WARNING in source.warnings for source in sources)
    if not missing:
        return ()
    return (
        ngettext(
            "{count} photo has no colour profile (treated as sRGB)",
            "{count} photos have no colour profile (treated as sRGB)",
            missing,
        ).format(count=missing),
    )


@dataclass(frozen=True, slots=True)
class PreflightInfo:
    """What the export dialog tells the user before anything is written."""

    total: int
    size_text: str = ""
    format_text: str = ""
    colour_text: str = ""
    metadata_text: str = ""
    destination: str = ""
    example: str = ""
    rename_example: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


def describe_preflight(
    snapshot: ExportJobSnapshot,
    *,
    rename_snapshot: ExportJobSnapshot | None = None,
    notes: Sequence[str] = (),
) -> PreflightInfo:
    """Summarise a planned job. ``rename_snapshot`` is the same job planned to keep both."""
    output = snapshot.output
    items = snapshot.items
    size_text = ""
    if items:
        plan = items[0].render_plan
        size_text = _("{width} × {height} px").format(width=plan.canvas_width, height=plan.canvas_height)
    format_text = output.format.upper()
    if output.format != "png":
        format_text = _("{format} · quality {quality}").format(format=format_text, quality=output.quality)
    example = ""
    for item in items:
        if item.action != "error":
            example = f"{item.source.path.name} → {item.destination.name}"
            break
    rename_example = ""
    if rename_snapshot is not None:
        for original, renamed in zip(items, rename_snapshot.items):
            if original.action == "skip":
                rename_example = renamed.destination.name
                break
    return PreflightInfo(
        total=len(items),
        size_text=size_text,
        format_text=format_text,
        colour_text=_("{space} (profile embedded)").format(space=output.color_space),
        metadata_text=metadata_summary(output.metadata),
        destination=clean_text(str(snapshot.output_dir)),
        example=example,
        rename_example=rename_example,
        notes=tuple(notes),
    )


class FramePresetDialog(QDialog):
    def __init__(
        self,
        preset: FramePreset,
        parent: QWidget | None = None,
        *,
        store: PresetStore | None = None,
        save_as: bool = False,
    ) -> None:
        super().__init__(parent)
        self._preset = preset
        self._store = store
        self._save_as_mode = save_as
        # The preset this dialog last wrote, so the caller can select it.
        self.saved_preset: FramePreset | None = None
        self.setWindowTitle(_("Save as Frame Preset") if save_as else _("Frame Preset"))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(_("{name} copy").format(name=preset.name) if save_as else preset.name)
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
        form.addRow(_("Name"), self.name_edit)
        form.addRow(_("Ratio width"), self.ratio_width_spin)
        form.addRow(_("Ratio height"), self.ratio_height_spin)
        form.addRow(_("Background"), self.background_edit)
        form.addRow("", background_presets)
        form.addRow(_("Photo Size"), self.scale_spin)
        form.addRow("", size_presets)
        form.addRow(_("X"), self.x_spin)
        form.addRow(_("Y"), self.y_spin)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.duplicate_button = QPushButton(_("Duplicate as Custom Preset"))
        self.save_button = QPushButton(_("Save"))
        self.save_as_button = QPushButton(_("Save As"))
        self.delete_button = QPushButton(_("Delete"))
        self.set_default_button = QPushButton(_("Set as Default"))
        self.save_preset_button = QPushButton(_("Save Preset"))
        self.save_preset_button.setObjectName("primaryButton")
        self.save_preset_button.setDefault(True)
        for button in (
            self.duplicate_button,
            self.save_button,
            self.save_as_button,
            self.delete_button,
            self.set_default_button,
            self.save_preset_button,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            if save_as
            else QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.duplicate_button.clicked.connect(self._duplicate)
        self.save_button.clicked.connect(lambda: self._save(save_as=False))
        self.save_as_button.clicked.connect(lambda: self._save(save_as=True))
        self.delete_button.clicked.connect(self._delete)
        self.set_default_button.clicked.connect(self.set_as_default)
        self.save_preset_button.clicked.connect(lambda: self._save(save_as=True))
        self._refresh_action_buttons()

    def _apply_background(self, color: str) -> None:
        normalized = normalize_hex_color(color)
        if normalized is not None:
            self.background_edit.setText(normalized)

    def _pick_background(self) -> None:
        current = QColor(self.background_edit.text() or self._preset.background)
        chosen = QColorDialog.getColor(current, self, _("Frame background"))
        if chosen.isValid():
            self._apply_background(chosen.name())

    def _refresh_action_buttons(self) -> None:
        builtin = self._preset.builtin
        if self._save_as_mode:
            # Saving the working frame only ever makes a new preset.
            self.duplicate_button.setVisible(False)
            self.save_button.setVisible(False)
            self.save_as_button.setVisible(False)
            self.delete_button.setVisible(False)
            self.set_default_button.setVisible(False)
            self.save_preset_button.setVisible(True)
            return
        self.save_preset_button.setVisible(False)
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
        self.saved_preset = preset
        self._refresh_action_buttons()

    def _duplicate(self) -> None:
        # Name the copy so it can be told apart from the preset it came from.
        if self.name_edit.text().strip() == self._preset.name:
            self.name_edit.setText(_("{name} copy").format(name=self._preset.name))
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
        info: PreflightInfo | None = None,
    ) -> None:
        super().__init__(parent)
        self._counts = counts
        self._info = info
        total = info.total if info is not None else counts.exportable + counts.conflicted
        export_title = ngettext("Export {count} photo", "Export {count} photos", total).format(count=total)
        self.setWindowTitle(export_title)
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.title_label = QLabel(export_title)
        self.title_label.setObjectName("sectionLabel")
        layout.addWidget(self.title_label)

        self.detail_labels: dict[str, QLabel] = {}
        if info is not None:
            form = QFormLayout()
            form.setHorizontalSpacing(14)
            rows = (
                ("Output size", _("Output size"), info.size_text),
                ("Format", _("Format"), info.format_text),
                ("Colour", _("Colour"), info.colour_text),
                ("Metadata", _("Metadata"), info.metadata_text),
                ("Destination", _("Destination"), info.destination),
                ("Example", _("Example"), info.example),
            )
            for caption, shown, value in rows:
                if not value:
                    continue
                label = QLabel(value)
                # Paths break badly at a backslash; let the dialog grow instead.
                label.setWordWrap(caption not in ("Destination", "Example"))
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.detail_labels[caption] = label
                form.addRow(_("{caption}:").format(caption=shown), label)
            layout.addLayout(form)
        self.notes_label = QLabel("\n".join(info.notes) if info is not None else "")
        self.notes_label.setWordWrap(True)
        self.notes_label.setObjectName("mutedLabel")
        self.notes_label.setVisible(bool(self.notes_label.text()))
        layout.addWidget(self.notes_label)
        self.invalid_label = QLabel(
            ngettext(
                "{count} photo can't be exported and will be left out.",
                "{count} photos can't be exported and will be left out.",
                counts.invalid,
            ).format(count=counts.invalid)
        )
        self.invalid_label.setWordWrap(True)
        self.invalid_label.setVisible(counts.invalid > 0)
        layout.addWidget(self.invalid_label)
        self.originals_label = QLabel(_("Originals are never changed."))
        self.originals_label.setObjectName("mutedLabel")
        layout.addWidget(self.originals_label)

        existing = _("Skip existing ({files} already exported)").format(
            files=ngettext("{count} file", "{count} files", counts.conflicted).format(count=counts.conflicted)
        )
        example = info.rename_example if info is not None else ""
        keep = (
            _("Keep both — save as {example}").format(example=example)
            if example
            else _("Keep both — number the new files")
        )
        self.skip_radio = QRadioButton(existing)
        self.rename_radio = QRadioButton(keep)
        self._policy_group = QButtonGroup(self)
        self._policy_group.setExclusive(True)
        self._policy_group.addButton(self.skip_radio)
        self._policy_group.addButton(self.rename_radio)
        self.conflict_prompt = QLabel(_("Some files are already in the output folder:"))
        if has_conflicts:
            layout.addWidget(self.conflict_prompt)
            layout.addWidget(self.skip_radio)
            layout.addWidget(self.rename_radio)
            self.skip_radio.setChecked(True)
        else:
            self.rename_radio.setChecked(True)
            self.conflict_prompt.hide()
            self.skip_radio.hide()
            self.rename_radio.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.export_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.export_button.setObjectName("primaryButton")
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

    def export_count(self) -> int:
        """How many photos the chosen policy will write."""
        exportable = self._counts.exportable
        if self.collision_policy() == "rename":
            exportable += self._counts.conflicted
        return exportable

    def _refresh_export_enabled(self) -> None:
        policy = self.collision_policy()
        count = self.export_count()
        self.export_button.setText(
            ngettext("Export {count} Photo", "Export {count} Photos", count).format(count=count)
        )
        if policy is None:
            self.export_button.setEnabled(False)
            return
        self.export_button.setEnabled(count > 0)


def completion_title(result: ExportResult, cancelled_count: int) -> str:
    """Headline for the completion dialog: the outcome, not just 'complete'."""
    failed = max(0, result.failed - getattr(result, "cancelled_count", 0))
    exported = result.exported
    if cancelled_count or result.cancelled:
        total = exported + result.skipped + failed + cancelled_count
        return _("Export stopped — {exported} of {total} exported").format(exported=exported, total=total)
    if failed:
        return _("Exported {exported} of {total} — {failed} failed").format(
            exported=exported, total=exported + failed, failed=failed
        )
    if exported == 0 and result.skipped:
        return _("Nothing new to export — {count} skipped").format(count=result.skipped)
    return ngettext("Exported {count} photo", "Exported {count} photos", exported).format(count=exported)


def failure_lines(result: ExportResult) -> list[str]:
    """One 'name - reason' line per photo that failed (not the ones stopped early)."""
    lines = []
    for item in result.items:
        if item.state == "failed" and item.message != "not run: cancelled":
            reason = clean_text(item.message) or _("Could not be exported.")
            name = Path(item.source).name
            # The friendly messages usually name the photo already.
            lines.append(reason if reason.startswith(name) else f"{name} — {reason}")
    return lines


class ExportCompletionDialog(QDialog):
    def __init__(
        self,
        result: ExportResult,
        cancelled_count: int,
        output_directory,
        parent: QWidget | None = None,
        *,
        on_view_results: Callable[[], None] | None = None,
        view_results_available: bool = False,
    ) -> None:
        super().__init__(parent)
        self._output_directory = output_directory
        self._on_view_results = on_view_results
        title = completion_title(result, cancelled_count)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.summary_label = QLabel(title)
        self.summary_label.setObjectName("sectionLabel")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        notes = []
        if result.skipped:
            notes.append(
                ngettext(
                    "{count} photo skipped (already in the folder)",
                    "{count} photos skipped (already in the folder)",
                    result.skipped,
                ).format(count=result.skipped)
            )
        if cancelled_count:
            notes.append(
                ngettext(
                    "{count} photo not exported before you stopped",
                    "{count} photos not exported before you stopped",
                    cancelled_count,
                ).format(count=cancelled_count)
            )
        self.detail_label = QLabel(" · ".join(notes))
        self.detail_label.setWordWrap(True)
        self.detail_label.setObjectName("mutedLabel")
        self.detail_label.setVisible(bool(notes))
        layout.addWidget(self.detail_label)

        failures = failure_lines(result)
        self.failures_text = QPlainTextEdit("\n".join(failures))
        self.failures_text.setReadOnly(True)
        self.failures_text.setAccessibleName(_("Failed photos"))
        self.failures_text.setMinimumHeight(min(160, 40 + 22 * len(failures)))
        self.failures_text.setVisible(bool(failures))
        layout.addWidget(self.failures_text)

        row = QHBoxLayout()
        self.open_folder_button = QPushButton(_("Open Output Folder"))
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.job_results_button = QPushButton(_("View in Job Results"))
        self.job_results_button.clicked.connect(self._view_results)
        self.job_results_button.setVisible(view_results_available and on_view_results is not None)
        self.close_button = QPushButton(_("Close"))
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        row.addWidget(self.open_folder_button)
        row.addWidget(self.job_results_button)
        row.addStretch(1)
        row.addWidget(self.close_button)
        layout.addLayout(row)

    def set_job_results_available(self, available: bool) -> None:
        self.job_results_button.setVisible(available and self._on_view_results is not None)

    def _view_results(self) -> None:
        self.accept()
        if self._on_view_results is not None:
            self._on_view_results()

    def open_output_folder(self) -> None:
        if self._output_directory is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_directory)))
