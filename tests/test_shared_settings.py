from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ndex_common import settings as shared_settings
from src.config import ConfigManager


class SharedSettingsTests(unittest.TestCase):
    def test_section_roundtrip_preserves_other_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with patch.object(shared_settings, "settings_path", return_value=path):
                shared_settings.update_section("auto_selector", {"last_work_folder": "D:/Work"})
                shared_settings.update_section("image_manager", {"last_source": "D:/Shoot"})
                shared_settings.update_section("auto_selector", {"xmp_rating": 4})

                auto = shared_settings.get_section("auto_selector")
                manager = shared_settings.get_section("image_manager")

            self.assertEqual(auto["last_work_folder"], "D:/Work")
            self.assertEqual(auto["xmp_rating"], 4)
            self.assertEqual(manager["last_source"], "D:/Shoot")

    def test_get_section_applies_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with patch.object(shared_settings, "settings_path", return_value=path):
                section = shared_settings.get_section("auto_selector", {"xmp_rating": 5})
            self.assertEqual(section["xmp_rating"], 5)

    def test_config_manager_save_preserves_foreign_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "verify_mode": "sha256",
                        "auto_selector": {"last_work_folder": "D:/Work"},
                        "image_manager": {"last_source": "D:/Shoot"},
                    }
                ),
                encoding="utf-8",
            )

            manager = ConfigManager()
            manager.config_path = config_path
            manager.save({"verify_mode": "size", "dry_run": True})

            stored = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["verify_mode"], "size")
            self.assertTrue(stored["dry_run"])
            self.assertEqual(stored["auto_selector"]["last_work_folder"], "D:/Work")
            self.assertEqual(stored["image_manager"]["last_source"], "D:/Shoot")

    def test_metadata_extractor_reads_settings(self) -> None:
        from src.metadata import MetadataExtractor

        extractor = MetadataExtractor.from_settings(
            {"metadata_batch_size": 25, "metadata_batch_timeout_seconds": 120}
        )
        self.assertEqual(extractor.batch_size, 25)
        self.assertEqual(extractor.timeout_seconds, 120)

        fallback = MetadataExtractor.from_settings({})
        self.assertEqual(fallback.batch_size, MetadataExtractor.DEFAULT_BATCH_SIZE)
        self.assertEqual(fallback.timeout_seconds, MetadataExtractor.DEFAULT_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
