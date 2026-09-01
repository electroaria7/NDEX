from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ndex_frame.services.presets import PresetStore


class PresetStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.settings: dict[str, dict[str, str]] = {}

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_store(self) -> PresetStore:
        def reader(section: str, defaults: dict[str, str]) -> dict[str, str]:
            values = dict(defaults)
            values.update(self.settings.get(section, {}))
            return values

        def writer(section: str, values: dict[str, str]) -> None:
            self.settings.setdefault(section, {}).update(values)

        return PresetStore(self.root, reader, writer)

    def test_builtins_are_loaded_and_cannot_be_deleted(self) -> None:
        store = self.make_store()
        self.assertEqual(store.default_frame().id, "builtin.white-3x4")
        with self.assertRaises(ValueError):
            store.delete_custom("builtin.white-3x4", kind="frame")

    def test_frame_and_output_defaults_are_independent(self) -> None:
        store = self.make_store()
        custom = replace(store.default_frame(), id="custom.tight", name="Tight", builtin=False)
        store.save_frame(custom)
        store.set_default_frame(custom.id)
        self.assertEqual(store.default_frame().id, "custom.tight")
        self.assertEqual(store.default_output().id, "builtin.instagram-feed-hq")

    def test_custom_presets_round_trip_through_individual_json_files(self) -> None:
        store = self.make_store()
        custom = replace(store.default_frame(), id="custom.tight", name="Tight", builtin=False)
        store.save_frame(custom)

        stored = self.root / "presets" / "frame" / "custom.tight.json"
        self.assertTrue(stored.is_file())
        self.assertEqual(json.loads(stored.read_text(encoding="utf-8"))["id"], "custom.tight")
        self.assertEqual([preset.id for preset in store.list_frames()], ["builtin.white-3x4", "custom.tight"])

    def test_deleted_default_is_repaired_to_matching_builtin(self) -> None:
        store = self.make_store()
        custom = replace(store.default_output(), id="custom.web", name="Web", builtin=False)
        store.save_output(custom)
        store.set_default_output(custom.id)
        store.delete_custom(custom.id, kind="output")

        self.assertEqual(store.default_output().id, "builtin.instagram-feed-hq")
        self.assertEqual(self.settings["frame"]["default_output_id"], "builtin.instagram-feed-hq")

    def test_corrupt_custom_json_is_reported_without_hiding_valid_presets(self) -> None:
        store = self.make_store()
        custom = replace(store.default_frame(), id="custom.valid", name="Valid", builtin=False)
        store.save_frame(custom)
        corrupt = self.root / "presets" / "frame" / "custom.corrupt.json"
        corrupt.write_text("{not json", encoding="utf-8")

        self.assertEqual([preset.id for preset in store.list_frames()], ["builtin.white-3x4", "custom.valid"])
        self.assertEqual(len(store.errors), 1)
        self.assertEqual(store.errors[0].path, corrupt)

    def test_save_rejects_builtin_identifier_for_custom_preset(self) -> None:
        store = self.make_store()
        forbidden = replace(store.default_frame(), id="builtin.shadow", builtin=False)
        with self.assertRaises(ValueError):
            store.save_frame(forbidden)

    def test_custom_frame_json_cannot_shadow_builtin_default(self) -> None:
        store = self.make_store()
        malicious = self.root / "presets" / "frame" / "shadow.json"
        malicious.parent.mkdir(parents=True)
        malicious.write_text(
            json.dumps(
                {
                    "id": "builtin.white-3x4",
                    "name": "Shadowed frame",
                    "version": 1,
                    "ratio": {"width": 1, "height": 1},
                    "background": "#000000",
                    "photo_scale": 1.0,
                    "x": 0.0,
                    "y": 0.0,
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(store.default_frame().name, "White 3:4")
        self.assertEqual([preset.id for preset in store.list_frames()], ["builtin.white-3x4"])
        self.assertEqual(store.errors[0].path, malicious)

    def test_custom_output_json_cannot_shadow_builtin_default(self) -> None:
        store = self.make_store()
        malicious = self.root / "presets" / "output" / "shadow.json"
        malicious.parent.mkdir(parents=True)
        malicious.write_text(
            json.dumps(
                {
                    "id": "builtin.instagram-feed-hq",
                    "name": "Shadowed output",
                    "version": 1,
                    "sizing": {"mode": "fixed_width", "width": 720},
                    "format": "png",
                    "quality": 95,
                    "chroma_subsampling": "4:4:4",
                    "color_space": "sRGB",
                    "embed_icc": True,
                    "metadata": {"preserve_capture": True, "preserve_copyright": True, "remove_gps": True},
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(store.default_output().name, "Instagram Feed HQ")
        self.assertEqual([preset.id for preset in store.list_outputs()], ["builtin.instagram-feed-hq"])
        self.assertEqual(store.errors[0].path, malicious)


if __name__ == "__main__":
    unittest.main()
