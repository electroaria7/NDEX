"""User-facing wording shared by the Frame services and UI (no Qt types)."""

from __future__ import annotations

import errno
import re
from dataclasses import dataclass, field
from pathlib import Path

NO_PROFILE_WARNING = "No colour profile — treated as sRGB"
PROFILE_FAILED_WARNING = "Colour profile could not be applied — used a basic conversion"

RAW_HINT = "Frame needs JPG/PNG/TIFF — export them from your RAW editor first"

_DOUBLE_BACKSLASH = re.compile(r"\\{2,}")
_ERRNO_PREFIX = re.compile(r"^\[(?:Errno|WinError) \d+\]\s*")
_INCOMPLETE_HINTS = (
    "truncated",
    "cannot identify",
    "broken data",
    "decoder error",
    "unrecognized data stream",
    "unexpected end",
    "incomplete",
    "premature end",
)


def clean_text(text: str) -> str:
    """Drop the errno prefix and the doubled backslashes repr() puts in paths."""
    return _DOUBLE_BACKSLASH.sub(r"\\", _ERRNO_PREFIX.sub("", str(text).strip()))


def unreadable_message(name: str) -> str:
    return f"{name} isn't a readable image — re-export it from your editor."


def describe_error(
    error: BaseException | str,
    *,
    name: str = "",
    folder: Path | str | None = None,
) -> str:
    """Turn a raw exception into guidance the photographer can act on."""
    text = clean_text(str(error) or error.__class__.__name__ if not isinstance(error, str) else error)
    lowered = text.lower()
    code = getattr(error, "errno", None)
    where = str(folder) if folder else "that folder"
    subject = name or "This photo"

    if (
        isinstance(error, PermissionError)
        or code in (errno.EACCES, errno.EPERM)
        or "permission denied" in lowered
        or "access is denied" in lowered
        or "read-only" in lowered
    ):
        return f"Can't write to {where}. Pick another folder or check that it isn't read-only."
    if code == errno.ENOSPC or "no space left" in lowered or "not enough space" in lowered:
        return f"There isn't enough free space for {where}. Free up space or pick another folder."
    if isinstance(error, (FileNotFoundError, NotADirectoryError)) or code == errno.ENOENT:
        missing = str(getattr(error, "filename", "") or "")
        if name and name.lower() in (missing or lowered).lower() and (not folder or str(folder) not in missing):
            return f"{name} can't be found — it may have been moved or deleted."
        return f"The output folder {where} was not found. Choose another output folder."
    if any(hint in lowered for hint in _INCOMPLETE_HINTS):
        return f"{subject} looks incomplete — copy it from the card again."
    return f"{name}: {text}" if name else text


@dataclass(frozen=True, slots=True)
class ImportSummary:
    opened: int = 0
    raw_skipped: int = 0
    unsupported: int = 0
    unreadable: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return self.opened + self.raw_skipped + self.unsupported + len(self.unreadable)


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def import_status_text(summary: ImportSummary, origin: str = "") -> str:
    """One status line for any import: how many opened and what was left out."""
    source = f" from {origin}" if origin else ""
    if summary.total == 0:
        return f"No JPG, PNG or TIFF photos found{source}"
    if summary.opened == 0:
        head = f"No photos opened{source}"
    elif summary.opened == summary.total:
        head = f"Opened {_plural(summary.opened, 'photo')}{source}"
    else:
        head = f"Opened {summary.opened} of {summary.total}{source}"
    notes: list[str] = []
    if summary.raw_skipped:
        notes.append(f"{_plural(summary.raw_skipped, 'RAW file')} skipped ({RAW_HINT})")
    if summary.unsupported:
        notes.append(f"{_plural(summary.unsupported, 'unsupported file')} skipped")
    if len(summary.unreadable) == 1:
        notes.append(unreadable_message(summary.unreadable[0][0]))
    elif summary.unreadable:
        names = ", ".join(name for name, _reason in summary.unreadable[:2])
        more = len(summary.unreadable) - 2
        listed = f"{names} and {more} more" if more > 0 else names
        notes.append(f"{len(summary.unreadable)} files aren't readable images ({listed}) — re-export them from your editor.")
    return " · ".join([head, *notes])
