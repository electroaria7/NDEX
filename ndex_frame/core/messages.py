"""User-facing wording shared by the Frame services and UI (no Qt types)."""

from __future__ import annotations

import errno
import re
from dataclasses import dataclass, field
from pathlib import Path

from ndex_common.i18n import _, ngettext

NO_PROFILE_WARNING = "No colour profile — treated as sRGB"
PROFILE_FAILED_WARNING = "Colour profile could not be applied — used a basic conversion"

RAW_HINT = "Frame needs JPG/PNG/TIFF — export them from your RAW editor first"

# The English texts above are identifiers (stored on sources and compared); they are
# translated only when shown. These calls let the extractor find them.
_TRANSLATABLE = (
    _("No colour profile — treated as sRGB"),
    _("Colour profile could not be applied — used a basic conversion"),
    _("Frame needs JPG/PNG/TIFF — export them from your RAW editor first"),
)


def warning_text(text: str) -> str:
    """The translated form of a stored source warning (unknown text is returned as is)."""
    return _(text)


def raw_hint() -> str:
    return _("Frame needs JPG/PNG/TIFF — export them from your RAW editor first")


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
    return _("{name} isn't a readable image — re-export it from your editor.").format(name=name)


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
    where = str(folder) if folder else _("that folder")
    subject = name or _("This photo")

    if (
        isinstance(error, PermissionError)
        or code in (errno.EACCES, errno.EPERM)
        or "permission denied" in lowered
        or "access is denied" in lowered
        or "read-only" in lowered
    ):
        return _("Can't write to {folder}. Pick another folder or check that it isn't read-only.").format(folder=where)
    if code == errno.ENOSPC or "no space left" in lowered or "not enough space" in lowered:
        return _("There isn't enough free space for {folder}. Free up space or pick another folder.").format(folder=where)
    if isinstance(error, (FileNotFoundError, NotADirectoryError)) or code == errno.ENOENT:
        missing = str(getattr(error, "filename", "") or "")
        if name and name.lower() in (missing or lowered).lower() and (not folder or str(folder) not in missing):
            return _("{name} can't be found — it may have been moved or deleted.").format(name=name)
        return _("The output folder {folder} was not found. Choose another output folder.").format(folder=where)
    if any(hint in lowered for hint in _INCOMPLETE_HINTS):
        return _("{subject} looks incomplete — copy it from the card again.").format(subject=subject)
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


def import_status_text(summary: ImportSummary, origin: str = "") -> str:
    """One status line for any import: how many opened and what was left out."""
    source = _(" from {origin}").format(origin=origin) if origin else ""
    if summary.total == 0:
        return _("No JPG, PNG or TIFF photos found{source}").format(source=source)
    if summary.opened == 0:
        head = _("No photos opened{source}").format(source=source)
    elif summary.opened == summary.total:
        head = ngettext("Opened {count} photo{source}", "Opened {count} photos{source}", summary.opened).format(
            count=summary.opened, source=source
        )
    else:
        head = _("Opened {opened} of {total}{source}").format(
            opened=summary.opened, total=summary.total, source=source
        )
    notes: list[str] = []
    if summary.raw_skipped:
        notes.append(
            _("{files} skipped ({hint})").format(
                files=ngettext("{count} RAW file", "{count} RAW files", summary.raw_skipped).format(
                    count=summary.raw_skipped
                ),
                hint=raw_hint(),
            )
        )
    if summary.unsupported:
        notes.append(
            _("{files} skipped").format(
                files=ngettext("{count} unsupported file", "{count} unsupported files", summary.unsupported).format(
                    count=summary.unsupported
                )
            )
        )
    if len(summary.unreadable) == 1:
        notes.append(unreadable_message(summary.unreadable[0][0]))
    elif summary.unreadable:
        names = ", ".join(name for name, _reason in summary.unreadable[:2])
        more = len(summary.unreadable) - 2
        listed = _("{names} and {more} more").format(names=names, more=more) if more > 0 else names
        notes.append(
            _("{count} files aren't readable images ({listed}) — re-export them from your editor.").format(
                count=len(summary.unreadable), listed=listed
            )
        )
    return " · ".join([head, *notes])
