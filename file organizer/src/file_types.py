from __future__ import annotations

from pathlib import Path


BASE_FILE_TYPES = {
    "jpg": {
        "label": "JPG / JPEG",
        "extensions": {".jpg", ".jpeg"},
    },
}

RAW_BRANDS = {
    "canon": {
        "label": "Canon",
        "types": {
            "cr3": {"label": "Canon CR3", "extensions": {".cr3"}},
            "cr2": {"label": "Canon CR2", "extensions": {".cr2"}},
        },
    },
    "sony": {
        "label": "Sony",
        "types": {
            "arw": {"label": "Sony ARW", "extensions": {".arw"}},
            "srf": {"label": "Sony SRF", "extensions": {".srf"}},
            "sr2": {"label": "Sony SR2", "extensions": {".sr2"}},
        },
    },
    "nikon": {
        "label": "Nikon",
        "types": {
            "nef": {"label": "Nikon NEF", "extensions": {".nef"}},
            "nrw": {"label": "Nikon NRW", "extensions": {".nrw"}},
        },
    },
}

FILE_TYPE_ORDER = ["jpg", "cr3", "cr2", "arw", "srf", "sr2", "nef", "nrw"]


def get_file_type_definitions() -> dict[str, dict]:
    definitions = dict(BASE_FILE_TYPES)
    for brand in RAW_BRANDS.values():
        definitions.update(brand["types"])
    return definitions


def get_extensions_for_types(enabled_types: list[str]) -> set[str]:
    definitions = get_file_type_definitions()
    extensions: set[str] = set()
    for file_type in enabled_types:
        file_type_definition = definitions.get(file_type)
        if file_type_definition:
            extensions.update(file_type_definition["extensions"])
    return extensions


def get_file_type_for_path(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    for file_type, definition in get_file_type_definitions().items():
        if ext in definition["extensions"]:
            return file_type
    return "others"


def get_file_type_label(file_type: str) -> str:
    definition = get_file_type_definitions().get(file_type)
    return definition["label"] if definition else file_type.upper()


def get_visible_file_types(enabled_brands: dict[str, bool]) -> list[str]:
    visible = ["jpg"]
    for brand_key, brand in RAW_BRANDS.items():
        if not enabled_brands.get(brand_key, False):
            continue
        visible.extend(brand["types"].keys())
    return [file_type for file_type in FILE_TYPE_ORDER if file_type in visible]
