"""Single definition of the camera RAW formats NDEX understands.

Every app builds its RAW extension list from ``RAW_FORMATS`` so a format is
added (or fixed) in exactly one place. Extensions are lower-case with the dot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RawFormat:
    extension: str
    brand: str
    brand_label: str
    name: str

    @property
    def type_key(self) -> str:
        """Lower-case extension without the dot: the NDEX One type/folder key."""
        return self.extension.lstrip(".")


def _fmt(extension: str, brand: str, brand_label: str, name: str) -> tuple[str, RawFormat]:
    return extension, RawFormat(extension, brand, brand_label, name)


# Order matters: it is the display order inside a brand.
RAW_FORMATS: dict[str, RawFormat] = dict(
    [
        _fmt(".cr3", "canon", "Canon", "Canon RAW (CR3)"),
        _fmt(".cr2", "canon", "Canon", "Canon RAW (CR2)"),
        _fmt(".crw", "canon", "Canon", "Canon RAW (CRW)"),
        _fmt(".arw", "sony", "Sony", "Sony Alpha RAW (ARW)"),
        _fmt(".srf", "sony", "Sony", "Sony RAW (SRF)"),
        _fmt(".sr2", "sony", "Sony", "Sony RAW (SR2)"),
        _fmt(".nef", "nikon", "Nikon", "Nikon RAW (NEF)"),
        _fmt(".nrw", "nikon", "Nikon", "Nikon Coolpix RAW (NRW)"),
        _fmt(".dng", "adobe", "Adobe", "Digital Negative (DNG)"),
    ]
)

RAW_EXTENSIONS: frozenset[str] = frozenset(RAW_FORMATS)

# Brands that have their own checkbox in NDEX One, in display order.
BRAND_ORDER = ("canon", "sony", "nikon")


def is_raw_path(path: Path | str) -> bool:
    return Path(path).suffix.casefold() in RAW_FORMATS


def raw_format_for(path: Path | str) -> RawFormat | None:
    return RAW_FORMATS.get(Path(path).suffix.casefold())


def extensions_for_brand(brand: str) -> list[str]:
    return [ext for ext, fmt in RAW_FORMATS.items() if fmt.brand == brand]
