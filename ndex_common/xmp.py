"""Shared XMP sidecar writer.

XMP is the common data contract between NDEX apps (Adobe-style interop):
Image Manager exports rating/pick state, Auto Selector marks selected RAW
files, and Lightroom/Evoto read the same sidecars. Sidecars are written
next to the target file; the target file itself is never modified.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

XMP_NS = "http://ns.adobe.com/xap/1.0/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC_NS = "http://purl.org/dc/elements/1.1/"
X_NS = "adobe:ns:meta/"

ET.register_namespace("x", X_NS)
ET.register_namespace("rdf", RDF_NS)
ET.register_namespace("xmp", XMP_NS)
ET.register_namespace("dc", DC_NS)


def write_xmp_sidecar(
    target_path: Path,
    *,
    rating: int | None = None,
    label: str | None = None,
    keywords: Iterable[str] = (),
) -> Path:
    """Write or merge an XMP sidecar next to ``target_path``.

    Existing sidecars are merged: unknown fields are preserved, and the
    fields passed here are updated. Returns the sidecar path.
    """
    xmp_path = target_path.with_suffix(".xmp")
    tree, description = _load_or_create(xmp_path)

    if rating is not None:
        clamped = max(0, min(5, int(rating)))
        description.set(f"{{{XMP_NS}}}Rating", str(clamped))
    if label:
        description.set(f"{{{XMP_NS}}}Label", label.strip())
    description.set(f"{{{XMP_NS}}}MetadataDate", datetime.now(timezone.utc).isoformat())

    for keyword in keywords:
        keyword = (keyword or "").strip()
        if keyword:
            _ensure_subject_keyword(description, keyword)

    _indent_xml(tree.getroot())
    tree.write(xmp_path, encoding="utf-8", xml_declaration=True)
    return xmp_path


def _load_or_create(xmp_path: Path) -> tuple[ET.ElementTree, ET.Element]:
    if xmp_path.exists():
        try:
            tree = ET.parse(xmp_path)
            description = _find_or_create_description(tree.getroot())
            return tree, description
        except ET.ParseError:
            pass
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
