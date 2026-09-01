from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import QApplication, QRadioButton

from ndex_frame.core.models import AspectRatio, FramePreset, MetadataPolicy, OutputProfile, OutputSizing
from ndex_frame.services.presets import PresetStore
from ndex_frame.ui.preset_dialog import ExportPreflightDialog, FramePresetDialog, PreflightCounts
from ndex_frame.ui.profile_dialog import OutputProfileDialog, custom_preset_id


class ProfileDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.instagram_profile = OutputProfile(
            "builtin.instagram-feed-hq",
            "Instagram Feed HQ",
            1,
            OutputSizing("fixed_width", width=1080),
            "jpeg",
            95,
            "4:4:4",
            "sRGB",
            True,
            MetadataPolicy(),
            True,
        )

    def test_profile_dialog_shows_computed_dimensions(self) -> None:
        dialog = OutputProfileDialog(self.instagram_profile, AspectRatio(3, 4))
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.computed_size_label.text(), "1080 × 1440")

    def test_builtin_profile_save_creates_custom_copy(self) -> None:
        dialog = OutputProfileDialog(self.instagram_profile, AspectRatio(3, 4))
        self.addCleanup(dialog.close)
        dialog.name_edit.setText("Instagram Feed HQ Custom")
        saved = dialog.build_profile()
        self.assertTrue(saved.id.startswith("custom."))
        self.assertFalse(saved.builtin)

    def test_basic_and_advanced_sections_expose_profile_fields(self) -> None:
        dialog = OutputProfileDialog(self.instagram_profile, AspectRatio(3, 4))
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.basic_group.title(), "Basic")
        self.assertEqual(dialog.advanced_group.title(), "Advanced")
        self.assertEqual(dialog.format_combo.currentData(), "jpeg")
        self.assertEqual(dialog.quality_spin.value(), 95)
        self.assertEqual(dialog.chroma_combo.currentData(), "4:4:4")
        self.assertEqual(dialog.color_space_combo.currentData(), "sRGB")
        self.assertTrue(dialog.embed_icc_checkbox.isChecked())
        dialog.quality_spin.setValue(80)
        dialog.embed_icc_checkbox.setChecked(False)
        saved = dialog.build_profile()
        self.assertEqual(saved.quality, 80)
        self.assertFalse(saved.embed_icc)

    def test_builtin_actions_duplicate_custom_actions_save(self) -> None:
        builtin = OutputProfileDialog(self.instagram_profile, AspectRatio(3, 4))
        self.addCleanup(builtin.close)
        self.assertEqual(builtin.duplicate_button.text(), "Duplicate as Custom Preset")
        self.assertFalse(builtin.duplicate_button.isHidden())
        self.assertTrue(builtin.save_button.isHidden())
        self.assertTrue(builtin.save_as_button.isHidden())
        self.assertTrue(builtin.delete_button.isHidden())

        custom_profile = replace(self.instagram_profile, id="custom.web", name="Web", builtin=False)
        custom = OutputProfileDialog(custom_profile, AspectRatio(3, 4))
        self.addCleanup(custom.close)
        self.assertTrue(custom.duplicate_button.isHidden())
        self.assertEqual(custom.save_button.text(), "Save")
        self.assertEqual(custom.save_as_button.text(), "Save As")
        self.assertEqual(custom.delete_button.text(), "Delete")
        self.assertFalse(custom.save_button.isHidden())

    def test_set_as_default_writes_only_selected_kind(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings: dict[str, dict[str, str]] = {}

        def reader(section: str, defaults: dict[str, str]) -> dict[str, str]:
            values = dict(defaults)
            values.update(settings.get(section, {}))
            return values

        def writer(section: str, values: dict[str, str]) -> None:
            settings.setdefault(section, {}).update(values)

        store = PresetStore(Path(temporary.name), reader, writer)
        custom_output = replace(store.default_output(), id="custom.web", name="Web", builtin=False)
        custom_frame = replace(store.default_frame(), id="custom.tight", name="Tight", builtin=False)
        store.save_output(custom_output)
        store.save_frame(custom_frame)

        output_dialog = OutputProfileDialog(custom_output, AspectRatio(3, 4), store=store)
        self.addCleanup(output_dialog.close)
        output_dialog.set_as_default()
        self.assertEqual(store.default_output().id, "custom.web")
        self.assertEqual(store.default_frame().id, "builtin.white-3x4")

        frame_dialog = FramePresetDialog(custom_frame, store=store)
        self.addCleanup(frame_dialog.close)
        frame_dialog.set_as_default()
        self.assertEqual(store.default_frame().id, "custom.tight")
        self.assertEqual(store.default_output().id, "custom.web")

    def test_builtin_frame_save_creates_custom_copy(self) -> None:
        frame = FramePreset(
            "builtin.white-3x4", "White 3:4", 1, AspectRatio(3, 4), "#FFFFFF", 1.0, 0.0, 0.0, True
        )
        dialog = FramePresetDialog(frame)
        self.addCleanup(dialog.close)
        dialog.name_edit.setText("White 3:4 Tight")
        saved = dialog.build_preset()
        self.assertTrue(saved.id.startswith("custom."))
        self.assertFalse(saved.builtin)
        self.assertEqual(saved.name, "White 3:4 Tight")

    def test_custom_preset_ids_are_unique_for_non_ascii_and_duplicate_names(self) -> None:
        first_korean = custom_preset_id("첫 번째")
        second_korean = custom_preset_id("두 번째", {first_korean})
        self.assertTrue(first_korean.startswith("custom."))
        self.assertTrue(second_korean.startswith("custom."))
        self.assertNotEqual(first_korean, second_korean)

        first_copy = custom_preset_id("Instagram Feed HQ")
        second_copy = custom_preset_id("Instagram Feed HQ", {first_copy})
        self.assertTrue(first_copy.startswith("custom."))
        self.assertTrue(second_copy.startswith("custom."))
        self.assertNotEqual(first_copy, second_copy)

    def test_duplicate_and_non_ascii_saves_do_not_overwrite_custom_presets(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings: dict[str, dict[str, str]] = {}

        def reader(section: str, defaults: dict[str, str]) -> dict[str, str]:
            values = dict(defaults)
            values.update(settings.get(section, {}))
            return values

        def writer(section: str, values: dict[str, str]) -> None:
            settings.setdefault(section, {}).update(values)

        store = PresetStore(Path(temporary.name), reader, writer)
        for name in ("첫 번째", "두 번째"):
            dialog = OutputProfileDialog(self.instagram_profile, AspectRatio(3, 4), store=store)
            self.addCleanup(dialog.close)
            dialog.name_edit.setText(name)
            dialog._duplicate()

        korean = [preset for preset in store.list_outputs() if preset.name in {"첫 번째", "두 번째"}]
        self.assertEqual({preset.name for preset in korean}, {"첫 번째", "두 번째"})
        self.assertEqual(len({preset.id for preset in korean}), 2)
        self.assertTrue(all(preset.id.startswith("custom.") and not preset.builtin for preset in korean))

        OutputProfileDialog(self.instagram_profile, AspectRatio(3, 4), store=store)._duplicate()
        OutputProfileDialog(self.instagram_profile, AspectRatio(3, 4), store=store)._duplicate()
        instagram_copies = [
            preset
            for preset in store.list_outputs()
            if preset.name == "Instagram Feed HQ" and not preset.builtin
        ]
        self.assertEqual(len(instagram_copies), 2)
        self.assertEqual(len({preset.id for preset in instagram_copies}), 2)
        self.assertTrue(all(preset.id.startswith("custom.") for preset in instagram_copies))

    def test_preflight_dialog_requires_skip_or_rename_without_overwrite(self) -> None:
        dialog = ExportPreflightDialog(PreflightCounts(1, 0, 2, 0), has_conflicts=True)
        self.addCleanup(dialog.close)
        texts = [dialog.exportable_label.text(), dialog.skipped_label.text(), dialog.conflicted_label.text(), dialog.invalid_label.text()]
        self.assertEqual(texts, ["Exportable: 1", "Skipped: 0", "Conflicted: 2", "Invalid: 0"])
        self.assertEqual(dialog.skip_radio.text(), "Skip existing")
        self.assertEqual(dialog.rename_radio.text(), "Auto rename")
        self.assertIsNone(dialog.collision_policy())
        self.assertFalse(dialog.export_button.isEnabled())
        radios = dialog.findChildren(QRadioButton)
        self.assertTrue(all("overwrite" not in radio.text().lower() for radio in radios))
        dialog.rename_radio.setChecked(True)
        self.assertEqual(dialog.collision_policy(), "rename")
        self.assertTrue(dialog.export_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
