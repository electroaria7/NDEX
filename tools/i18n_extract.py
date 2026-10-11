"""Collect translatable strings and sync them into ndex_common/locales/*.json.

Scans Python sources with ``ast`` for ``_("...")`` and ``ngettext("sing", "plur", n)``
calls whose text arguments are string literals, then:

* adds every missing key to each locale file with an empty value (empty means
  untranslated, so the app shows the English text);
* reports keys that no source uses any more (``--prune`` deletes them);
* ``--check`` writes nothing and exits 1 when a locale is missing keys.

Usage::

    python tools/i18n_extract.py [--locales DIR] [--prune] [--check] [SOURCE_DIR ...]

With no sources it scans the repository's app packages.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LOCALES = REPO / "ndex_common" / "locales"
DEFAULT_SOURCES = [
    "ndex_common", "ndex_launcher", "ndex_frame", "dsb_image_manager",
    "ndex_auto_selector", "ndex_one", "main.py",
]
SKIP_DIRS = {".venv", "venv", "build", "dist", "__pycache__", ".git", "tests", "node_modules"}
META_KEY = "__meta__"
PLURAL_KEY = "__plural__"


def _literal(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_source(source: str) -> tuple[set[str], set[str]]:
    """``(messages, plural singulars)`` found in one module's source text."""
    messages: set[str] = set()
    plurals: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if name == "_" and node.args:
            text = _literal(node.args[0])
            if text:
                messages.add(text)
        elif name == "ngettext" and len(node.args) >= 2:
            singular, plural = _literal(node.args[0]), _literal(node.args[1])
            if singular and plural:
                plurals.add(singular)
    return messages, plurals


def iter_python_files(roots: list[Path]):
    for root in roots:
        if root.is_file():
            yield root
            continue
        for path in sorted(root.rglob("*.py")):
            if not SKIP_DIRS.intersection(path.relative_to(root).parts[:-1]):
                yield path


def extract_tree(roots: list[Path]) -> tuple[set[str], set[str]]:
    messages: set[str] = set()
    plurals: set[str] = set()
    for path in iter_python_files(roots):
        try:
            found, found_plurals = extract_source(path.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            print(f"skip {path}: {exc}", file=sys.stderr)
            continue
        messages |= found
        plurals |= found_plurals
    return messages, plurals


def sync_locale(data: dict, messages: set[str], plurals: set[str], prune: bool) -> tuple[dict, list[str], list[str]]:
    """Return ``(new data, added keys, unused keys)`` without touching ``data``."""
    entries = {k: v for k, v in data.items() if k not in (META_KEY, PLURAL_KEY)}
    stored_plurals = data.get(PLURAL_KEY) if isinstance(data.get(PLURAL_KEY), dict) else {}
    plural_entries = dict(stored_plurals)

    added = sorted(k for k in messages if k not in entries)
    added += sorted(f"{k} (plural)" for k in plurals if k not in plural_entries)
    unused = sorted(k for k in entries if k not in messages)
    unused += sorted(f"{k} (plural)" for k in plural_entries if k not in plurals)

    for key in messages:
        entries.setdefault(key, "")
    for key in plurals:
        plural_entries.setdefault(key, ["", ""])
    if prune:
        entries = {k: v for k, v in entries.items() if k in messages}
        plural_entries = {k: v for k, v in plural_entries.items() if k in plurals}

    result: dict = {}
    if META_KEY in data:
        result[META_KEY] = data[META_KEY]
    for key in sorted(entries):
        result[key] = entries[key]
    if plural_entries:
        result[PLURAL_KEY] = {k: plural_entries[k] for k in sorted(plural_entries)}
    return result, added, unused


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sources", nargs="*", help="folders or files to scan")
    parser.add_argument("--locales", type=Path, default=DEFAULT_LOCALES, help="locale folder to update")
    parser.add_argument("--prune", action="store_true", help="delete keys no source uses")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if keys are missing")
    args = parser.parse_args(argv)

    roots = [Path(s) for s in args.sources] or [REPO / s for s in DEFAULT_SOURCES if (REPO / s).exists()]
    messages, plurals = extract_tree(roots)
    print(f"Found {len(messages)} messages and {len(plurals)} plural messages.")

    missing_total = 0
    for path in sorted(args.locales.glob("*.json")):
        if path.stem == "en":
            continue  # English is the source text itself; it needs no entries.
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            print(f"{path.name}: unreadable ({exc})", file=sys.stderr)
            return 2
        if not isinstance(data, dict):
            print(f"{path.name}: not a JSON object", file=sys.stderr)
            return 2
        result, added, unused = sync_locale(data, messages, plurals, args.prune)
        missing_total += len(added)
        print(f"{path.name}: {len(added)} missing, {len(unused)} unused" + (" (pruned)" if args.prune and unused else ""))
        for key in unused:
            print(f"  unused: {key}")
        if args.check:
            for key in added:
                print(f"  missing: {key}")
        elif result != data or args.prune:
            text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
    if args.check and missing_total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
