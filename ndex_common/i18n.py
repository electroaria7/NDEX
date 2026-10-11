"""Small gettext-style localization shared by every NDEX app.

The English source text is the key::

    from ndex_common.i18n import _, ngettext

    _("Open")
    _("Copied {count} files").format(count=n)
    ngettext("{count} file", "{count} files", n).format(count=n)

Translations live in ``ndex_common/locales/<code>.json`` (flat
``{"English": "translation"}`` objects) and in the user override folder
``%LOCALAPPDATA%/NDEX/locales``; a user file overrides the bundled one per key.
A missing key, an empty translation, or an unknown language returns the
English text unchanged. Lookups never raise.

Call ``init(app_name)`` once at app start. Until then (and in tools/tests that
never call it) every lookup returns the English text.
"""

from __future__ import annotations

import json
import locale
import sys
from pathlib import Path

from ndex_common.settings import data_dir, get_section, update_section

SYSTEM = "system"
DEFAULT_LANGUAGE = "en"
SETTINGS_SECTION = "shared"
SETTINGS_KEY = "language"
META_KEY = "__meta__"
PLURAL_KEY = "__plural__"

# Windows primary language ids (LANGID & 0x3ff) -> locale codes.
_PRIMARY_LANGID = {
    0x04: "zh", 0x07: "de", 0x09: "en", 0x0A: "es", 0x0C: "fr", 0x10: "it",
    0x11: "ja", 0x12: "ko", 0x15: "pl", 0x16: "pt", 0x19: "ru", 0x1F: "tr",
}
_LANGUAGE_NAMES = {
    "chinese": "zh", "german": "de", "english": "en", "spanish": "es", "french": "fr",
    "italian": "it", "japanese": "ja", "korean": "ko", "polish": "pl",
    "portuguese": "pt", "russian": "ru", "turkish": "tr",
}

_language = DEFAULT_LANGUAGE
_messages: dict[str, str] = {}
_plurals: dict[str, list[str]] = {}


# --------------------------------------------------------------------- lookup


def _(text: str) -> str:
    """Translate ``text``; return it unchanged when no translation exists."""
    try:
        found = _messages.get(text)
        return found if found else text
    except Exception:
        return text


def ngettext(singular: str, plural: str, n: int) -> str:
    """Pick the singular or plural form for ``n``, translated when possible."""
    try:
        forms = _plurals.get(singular)
        if forms:
            found = forms[min(0 if n == 1 else 1, len(forms) - 1)]
            if found:
                return found
    except Exception:
        pass
    return singular if n == 1 else plural


# ------------------------------------------------------------------ locations


def bundled_locales_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    root = Path(base) / "ndex_common" if base else Path(__file__).resolve().parent
    return root / "locales"


def override_locales_dir() -> Path:
    """``%LOCALAPPDATA%/NDEX/locales`` - user files override bundled ones."""
    return data_dir() / "locales"


def _locale_dirs() -> list[Path]:
    return [bundled_locales_dir(), override_locales_dir()]


def _read_locale(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _locale_files(code: str) -> list[Path]:
    return [folder / f"{code}.json" for folder in _locale_dirs()]


# ------------------------------------------------------------------ languages


def available_languages() -> list[tuple[str, str]]:
    """``[(code, display name)]`` for every discovered locale file, English first."""
    names: dict[str, str] = {DEFAULT_LANGUAGE: "English"}
    for folder in _locale_dirs():
        try:
            files = sorted(folder.glob("*.json"))
        except OSError:
            continue
        for path in files:
            code = path.stem.lower()
            meta = _read_locale(path).get(META_KEY)
            name = meta.get("name") if isinstance(meta, dict) else None
            if isinstance(name, str) and name.strip():
                names[code] = name.strip()
            else:
                names.setdefault(code, code)
    codes = sorted(names, key=lambda code: (code != DEFAULT_LANGUAGE, code))
    return [(code, names[code]) for code in codes]


def system_language() -> str:
    """The Windows UI language as a two-letter code (``en`` when unknown)."""
    try:
        import ctypes

        langid = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())  # type: ignore[attr-defined]
        code = _PRIMARY_LANGID.get(langid & 0x3FF)
        if code:
            return code
    except Exception:
        pass
    try:
        name = (locale.getlocale()[0] or "").strip().lower()
    except Exception:
        name = ""
    if name:
        head = name.replace("-", "_").split("_", 1)[0]
        return _LANGUAGE_NAMES.get(head, head[:2]) or DEFAULT_LANGUAGE
    return DEFAULT_LANGUAGE


def configured_language() -> str:
    """The stored choice: ``"system"`` or an explicit code."""
    try:
        value = get_section(SETTINGS_SECTION).get(SETTINGS_KEY)
    except Exception:
        return SYSTEM
    return value.strip().lower() if isinstance(value, str) and value.strip() else SYSTEM


def set_language(code: str) -> None:
    """Persist the language choice; it applies on the next app start."""
    value = (code or SYSTEM).strip().lower() or SYSTEM
    update_section(SETTINGS_SECTION, {SETTINGS_KEY: value})


def current_language() -> str:
    """The language resolved at ``init`` (what ``_()`` is translating into)."""
    return _language


def resolve_language(choice: str | None = None) -> str:
    """Turn a stored choice into an available language code."""
    choice = (choice or configured_language()).strip().lower()
    if choice == SYSTEM:
        choice = system_language()
    known = {code for code, _name in available_languages()}
    return choice if choice in known else DEFAULT_LANGUAGE


def load_catalog(code: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Merge the bundled and override files for ``code``; empty entries are skipped."""
    messages: dict[str, str] = {}
    plurals: dict[str, list[str]] = {}
    for path in _locale_files(code):
        data = _read_locale(path)
        for key, value in data.items():
            if key == META_KEY:
                continue
            if key == PLURAL_KEY:
                if isinstance(value, dict):
                    for singular, forms in value.items():
                        if isinstance(forms, list) and any(isinstance(f, str) and f for f in forms):
                            plurals[singular] = [f if isinstance(f, str) else "" for f in forms]
                continue
            if isinstance(value, str) and value:
                messages[key] = value
    return messages, plurals


def init(app_name: str = "", language: str | None = None) -> str:
    """Resolve the language once at app start and load its translations.

    ``language`` overrides the stored setting (tests, command-line flags).
    Never raises; on any problem the app simply stays in English.
    """
    global _language, _messages, _plurals
    try:
        code = resolve_language(language)
        _messages, _plurals = load_catalog(code)
        _language = code
    except Exception:
        _language, _messages, _plurals = DEFAULT_LANGUAGE, {}, {}
    return _language


__all__ = [
    "_", "ngettext", "init", "available_languages", "current_language",
    "configured_language", "set_language", "system_language", "resolve_language",
]
