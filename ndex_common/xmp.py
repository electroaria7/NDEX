"""Shared XMP sidecar writer.

XMP is the common data contract between NDEX apps (Adobe-style interop):
Image Manager exports rating/pick state, Auto Selector marks selected RAW
files, and Lightroom/Evoto read the same sidecars. Sidecars are written
next to the target file; the target file itself is never modified.

Path rules:
- RAW masters use ``IMG_0001.xmp`` (Lightroom-compatible).
- JPG and other non-RAW files use ``IMG_0001.JPG.xmp`` so a paired RAW/JPG
  set never silently overwrites one sidecar with the other.
"""

from __future__ import annotations

import os
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

XMP_NS = "http://ns.adobe.com/xap/1.0/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC_NS = "http://purl.org/dc/elements/1.1/"
X_NS = "adobe:ns:meta/"

RAW_EXTENSIONS = {
    ".cr3",
    ".cr2",
    ".arw",
    ".srf",
    ".sr2",
    ".nef",
    ".nrw",
    ".dng",
}

ET.register_namespace("x", X_NS)
ET.register_namespace("rdf", RDF_NS)
ET.register_namespace("xmp", XMP_NS)
ET.register_namespace("dc", DC_NS)


def sidecar_path_for(target_path: Path) -> Path:
    """Return the canonical sidecar path for ``target_path``."""
    target_path = Path(target_path)
    if target_path.suffix.casefold() in RAW_EXTENSIONS:
        return target_path.with_suffix(".xmp")
    return Path(str(target_path) + ".xmp")


def sidecar_paths_for_read(target_path: Path) -> list[Path]:
    """Candidate sidecar paths, preferring the canonical name then legacy ``.xmp``."""
    primary = sidecar_path_for(target_path)
    legacy = Path(target_path).with_suffix(".xmp")
    if legacy == primary:
        return [primary]
    return [primary, legacy]


def write_xmp_sidecar(
    target_path: Path,
    *,
    rating: int | None = None,
    label: str | None = None,
    keywords: Iterable[str] = (),
    remove_keywords: Iterable[str] = (),
    clear_label_if: Iterable[str] = (),
) -> Path:
    """Write or merge an XMP sidecar next to ``target_path``.

    Existing sidecars are merged: unknown fields are preserved, and the
    fields passed here are updated. ``remove_keywords`` drops those keywords
    first, and ``clear_label_if`` clears the current label only when it is
    one of the given values (so labels the user chose are never deleted).
    Returns the sidecar path.
    """
    xmp_path = sidecar_path_for(target_path)
    tree, description = _load_or_create(target_path, xmp_path)

    _remove_subject_keywords(description, {(k or "").strip() for k in remove_keywords})
    _clear_label_if(description, {(v or "").strip() for v in clear_label_if})

    if rating is not None:
        clamped = max(0, min(5, int(rating)))
        _set_simple_property(description, "Rating", str(clamped))
    if label:
        _set_simple_property(description, "Label", label.strip())
    _set_simple_property(description, "MetadataDate", datetime.now(timezone.utc).isoformat())

    for keyword in keywords:
        keyword = (keyword or "").strip()
        if keyword:
            _ensure_subject_keyword(description, keyword)

    _indent_xml(tree.getroot())
    _write_atomic(xmp_path, tree)
    return xmp_path


def _write_atomic(xmp_path: Path, tree: ET.ElementTree) -> None:
    xmp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = xmp_path.with_name(f".{xmp_path.name}.{uuid.uuid4().hex}.ndex_tmp")
    try:
        tree.write(temp_path, encoding="utf-8", xml_declaration=True)
        os.replace(temp_path, xmp_path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _load_or_create(target_path: Path, xmp_path: Path) -> tuple[ET.ElementTree, ET.Element]:
    # Merge only from the sidecar this target owns. The legacy ``IMG_1.xmp``
    # next to a JPG belongs to the paired RAW, so it must not leak into
    # ``IMG_1.JPG.xmp``.
    for candidate in (xmp_path,):
        if not candidate.exists():
            continue
        try:
            tree = ET.parse(candidate)
            description = _find_or_create_description(tree.getroot())
            return tree, description
        except ET.ParseError:
            continue
    root, description = _new_xmp_tree()
    return ET.ElementTree(root), description


def _new_xmp_tree() -> tuple[ET.Element, ET.Element]:
    root = ET.Element(f"{{{X_NS}}}xmpmeta")
    rdf = ET.SubElement(root, f"{{{RDF_NS}}}RDF")
    description = ET.SubElement(rdf, f"{{{RDF_NS}}}Description")
    description.set(f"{{{RDF_NS}}}about", "")
    return root, description


def _find_or_create_description(root: ET.Element) -> ET.Element:
    description = root.find(f".//{{{RDF_NS}}}Description")
    if description is not None:
        return description

    rdf = root.find(f".//{{{RDF_NS}}}RDF")
    if rdf is None:
        rdf = ET.SubElement(root, f"{{{RDF_NS}}}RDF")
    description = ET.SubElement(rdf, f"{{{RDF_NS}}}Description")
    description.set(f"{{{RDF_NS}}}about", "")
    return description


def _set_simple_property(description: ET.Element, name: str, value: str) -> None:
    """Set an xmp: property as an attribute, dropping a child-element form of it."""
    tag = f"{{{XMP_NS}}}{name}"
    for child in description.findall(tag):
        description.remove(child)
    description.set(tag, value)


def _clear_label_if(description: ET.Element, owned: set[str]) -> None:
    owned = {value for value in owned if value}
    if not owned:
        return
    tag = f"{{{XMP_NS}}}Label"
    if (description.get(tag) or "").strip() in owned:
        del description.attrib[tag]
    for child in description.findall(tag):
        if (child.text or "").strip() in owned:
            description.remove(child)


def _remove_subject_keywords(description: ET.Element, keywords: set[str]) -> None:
    keywords = {keyword for keyword in keywords if keyword}
    if not keywords:
        return
    for subject in description.findall(f"{{{DC_NS}}}subject"):
        for container in list(subject):
            for item in container.findall(f"{{{RDF_NS}}}li"):
                if (item.text or "").strip() in keywords:
                    container.remove(item)
            if container.find(f"{{{RDF_NS}}}li") is None:
                subject.remove(container)
        if len(subject) == 0:
            description.remove(subject)


def _ensure_subject_keyword(description: ET.Element, keyword: str) -> None:
    subject = description.find(f"{{{DC_NS}}}subject")
    if subject is None:
        subject = ET.SubElement(description, f"{{{DC_NS}}}subject")

    bag = subject.find(f"{{{RDF_NS}}}Bag")
    if bag is None:
        bag = ET.SubElement(subject, f"{{{RDF_NS}}}Bag")

    existing = {item.text for item in bag.findall(f"{{{RDF_NS}}}li")}
    if keyword not in existing:
        li = ET.SubElement(bag, f"{{{RDF_NS}}}li")
        li.text = keyword


def _indent_xml(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "  "
    child_indent = "\n" + (level + 1) * "  "
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = child_indent
        for child in children:
            _indent_xml(child, level + 1)
        if not element.tail or not element.tail.strip():
            element.tail = indent
    elif level and (not element.tail or not element.tail.strip()):
        element.tail = indent
