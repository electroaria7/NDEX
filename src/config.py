from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .app_paths import get_default_settings_template_path, get_user_config_dir

DEFAULT_SETTINGS = {
    "supported_extensions": [".cr3", ".cr2", ".arw", ".srf", ".sr2", ".nef", ".nrw", ".jpg", ".jpeg"],
    "folder_pattern": "{YYYY}/{MM}/{MMDD}/{type}",
    "duplicate_policy": "rename",
    "verify_mode": "size",
    "dry_run": False,
    "use_exiftool": True,
    "fallback_to_modified_time": True,
    "metadata_batch_size": 50,
    "metadata_batch_timeout_seconds": 60,
    "default_file_types": {
        "jpg": True,
        "cr3": True,
        "cr2": True,
        "arw": True,
        "srf": True,
        "sr2": True,
        "nef": True,
        "nrw": True,
    },
    "raw_brands": {
        "canon": True,
        "sony": False,
        "nikon": False,
    },
    "last_source": "",
    "last_destination": "",
}


class ConfigManager:
    def __init__(self, root_dir: Path | None = None):
        self.root_dir = Path(root_dir) if root_dir else None
        self.config_path = get_user_config_dir() / "settings.json"

    def load(self) -> dict:
        data = deepcopy(DEFAULT_SETTINGS)
        template_path = get_default_settings_template_path()
        if template_path.exists():
            with template_path.open("r", encoding="utf-8") as handle:
                bundled = json.load(handle)
            data.update(bundled)
            self._merge_nested_settings(data, bundled)

        if not self.config_path.exists():
            self.save(data)
            return data

        with self.config_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        data.update(loaded)

        self._merge_nested_settings(data, loaded)
        return data

    def save(self, data: dict) -> None:
        from ndex_common.settings import atomic_update

        def mutator(existing: dict) -> dict:
            merged = deepcopy(DEFAULT_SETTINGS)
            merged.update(existing)
            self._merge_nested_settings(merged, existing)
            merged.update(data)
            self._merge_nested_settings(merged, data)
            return merged

        atomic_update(mutator, path=self.config_path)

    @staticmethod
    def _merge_nested_settings(target: dict, source: dict) -> None:
        for key in ("default_file_types", "raw_brands"):
            if key in source:
                merged = deepcopy(DEFAULT_SETTINGS[key])
                merged.update(source[key])
                target[key] = merged
