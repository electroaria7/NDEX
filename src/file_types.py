from __future__ import annotations

from pathlib import Path

from ndex_common.i18n import _
from ndex_common.raw_formats import BRAND_ORDER, RAW_FORMATS, extensions_for_brand


BASE_FILE_TYPES = {
    "jpg": {
        "label": "JPG",
        "extensions": {".jpg", ".jpeg"},
    },
}

def _build_raw_brands() -> dict[str, dict]:
    brands: dict[str, dict] = {}
    for brand_key in BRAND_ORDER:
        types = {}
        label = brand_key.title()
        for extension in extensions_for_brand(brand_key):
            fmt = RAW_FORMATS[extension]
            label = fmt.brand_label
            types[fmt.type_key] = {
                "label": f"{fmt.brand_label} RAW (.{fmt.type_key.upper()})",
                "brand": fmt.brand_label,
                "ext": fmt.type_key.upper(),
                "extensions": {extension},
            }
        brands[brand_key] = {"label": label, "types": types}
    return brands


# Checkbox brands for NDEX One. Built from ndex_common.raw_formats; the type key
# (lower-case extension) doubles as the on-disk type folder name.
RAW_BRANDS = _build_raw_brands()

FILE_TYPE_ORDER = ["jpg"] + [
    file_type for brand in RAW_BRANDS.values() for file_type in brand["types"]
]


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
    """Checkbox text for a type. The definition's English ``label`` stays the data."""
    definition = get_file_type_definitions().get(file_type)
    if definition is None:
        return file_type.upper()
    if "brand" in definition:
        return _("{brand} RAW (.{ext})").format(brand=definition["brand"], ext=definition["ext"])
    return definition["label"]


def get_file_type_group(file_type: str) -> str:
    """Short name for summaries: "JPG" for JPEGs, "RAW" for every camera RAW type."""
    return "JPG" if file_type == "jpg" else "RAW"


def get_visible_file_types(enabled_brands: dict[str, bool]) -> list[str]:
    visible = ["jpg"]
    for brand_key, brand in RAW_BRANDS.items():
        if not enabled_brands.get(brand_key, False):
            continue
        visible.extend(brand["types"].keys())
    return [file_type for file_type in FILE_TYPE_ORDER if file_type in visible]
