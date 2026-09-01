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
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["schema_version"], shared_settings.SCHEMA_VERSION)
            self.assertTrue(path.with_name("settings.json.bak").exists())

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
            self.assertEqual(stored["schema_version"], shared_settings.SCHEMA_VERSION)

    def test_migrate_coerces_non_dict_sections_and_stamps_schema(self) -> None:
        migrated = shared_settings.migrate(
            {"schema_version": "bogus", "image_manager": "not-a-dict", "verify_mode": "size"}
        )
        self.assertEqual(migrated["schema_version"], 1)
        self.assertEqual(migrated["image_manager"], {})
        self.assertEqual(migrated["verify_mode"], "size")

    def test_concurrent_section_updates_keep_both_sections(self) -> None:
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            errors: list[BaseException] = []

            def write_section(section: str, key: str) -> None:
                try:
                    for index in range(25):
                        shared_settings.update_section(section, {key: index})
                except BaseException as exc:  # pragma: no cover - failure is asserted below
                    errors.append(exc)

            with patch.object(shared_settings, "settings_path", return_value=path):
                workers = [
                    threading.Thread(target=write_section, args=("image_manager", "last_source")),
                    threading.Thread(target=write_section, args=("auto_selector", "xmp_rating")),
                ]
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join()
                stored = shared_settings.load_all()

            self.assertEqual(errors, [])
            self.assertEqual(stored["image_manager"]["last_source"], 24)
            self.assertEqual(stored["auto_selector"]["xmp_rating"], 24)
            self.assertEqual(stored["schema_version"], 1)

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
