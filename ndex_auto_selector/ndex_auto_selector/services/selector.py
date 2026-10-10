from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from threading import Event

from ndex_common.filecopy import copy_verified

from ndex_common.rating import read_jpg_rating
from ndex_common.retry import path_key
from ndex_common.xmp import sidecar_paths_for_read, write_xmp_sidecar

from ..core.models import AnalysisSummary, CopyResult, DuplicatePolicy, SelectionMatch

JPG_EXTENSIONS = {".jpg", ".jpeg"}
RAW_EXTENSIONS = {".cr3", ".cr2", ".arw", ".srf", ".sr2", ".nef", ".nrw"}
# An ID must not sit inside a longer token: no letter/digit before it and no
# further digit after it (IMG_1234 must not match IMG_12345).
CAMERA_ID_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])IMG_\d{4}(?!\d)", re.IGNORECASE),   # Canon: IMG_0001
    re.compile(r"(?<![A-Za-z0-9])_DSC\d{4}(?!\d)", re.IGNORECASE),   # Nikon (Adobe RGB): _DSC0001
    re.compile(r"(?<![A-Za-z0-9])DSC_\d{4}(?!\d)", re.IGNORECASE),   # Nikon (sRGB): DSC_0001
    re.compile(r"(?<![A-Za-z0-9])DSC\d{5}(?!\d)", re.IGNORECASE),    # Sony: DSC00001
)
CACHE_DIR_NAME = ".dsb_cache"


def load_handoff(manifest_path: Path) -> tuple[Path | None, list[Path]]:
    """Read an Image Manager select_handoff: (source folder, picked JPG files)."""
    from ndex_common.manifest import handoff_files, load_manifest

    manifest = load_manifest(Path(manifest_path))
    if manifest is None:
        raise ValueError(f"Not a valid handoff manifest: {manifest_path}")
    source = manifest.get("source") or (manifest.get("folders") or {}).get("source")
    files = [path for path in handoff_files(manifest) if path.suffix.casefold() in JPG_EXTENSIONS]
    return (Path(str(source)) if source else None), files


def _sha256(path: Path) -> bytes:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.digest()


def _identical_files(first: Path, second: Path) -> bool:
    try:
        if first.stat().st_size != second.stat().st_size:
            return False
        return _sha256(first) == _sha256(second)
    except OSError:
        return False


def _resolved(path: Path) -> Path:
    try:
        return Path(path).resolve()
    except OSError:
        return Path(path).absolute()


def _is_within(path: Path, folder: Path) -> bool:
    try:
        _resolved(path).relative_to(folder)
    except ValueError:
        return False
    return True
SELECTED_LABEL = "NDEX Selected"


class AnalysisCancelled(Exception):
    """A matching analysis was stopped before a complete result existed."""


def _check_cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelled()


def _walk_files(root: Path, recursive: bool, *, exclude: Path | None = None,
                skip_cache: bool = False, cancel_event: Event | None = None):
    """Prune excluded directories before entering them, including large caches."""
    excluded = _resolved(exclude) if exclude is not None else None
    if excluded is not None and _is_within(root, excluded):
        return

    def failed(error):
        raise error

    for folder, dirs, names in os.walk(root, topdown=True, onerror=failed):
        _check_cancelled(cancel_event)
        parent = Path(folder)
        dirs[:] = [name for name in dirs if recursive
                   and not (skip_cache and name.casefold() == CACHE_DIR_NAME)
                   and not (excluded is not None and _is_within(parent / name, excluded))]
        for name in names:
            _check_cancelled(cancel_event)
            yield parent / name


class AutoSelectorService:
    def analyze(
        self,
        raw_source_dir: Path,
        selected_jpg_dir: Path,
        recursive: bool = True,
        exclude: Path | None = None,
        jpg_files: list[Path] | None = None,
        cancel_event: Event | None = None,
    ) -> AnalysisSummary:
        """Match selected JPGs to RAWs.

        ``exclude`` (the work folder) is not indexed for RAWs, so copies made
        there never make later analyses ambiguous. ``jpg_files`` restricts the
        selection to exactly those files (an Image Manager handoff) instead of
        scanning ``selected_jpg_dir``.
        """
        raw_source_dir = Path(raw_source_dir)
        selected_jpg_dir = Path(selected_jpg_dir)
        self._require_dir(raw_source_dir, "CR3 source folder")
        self._require_dir(selected_jpg_dir, "selected JPG folder")

        _check_cancelled(cancel_event)
        raw_by_stem = self._index_cr3_files(
            raw_source_dir, recursive=recursive, exclude=exclude, cancel_event=cancel_event
        )
        if jpg_files is None:
            jpg_files = self._list_jpg_files(selected_jpg_dir, recursive=recursive, cancel_event=cancel_event)
        else:
            jpg_files = sorted(
                (
                    Path(path)
                    for path in jpg_files
                    if Path(path).suffix.casefold() in JPG_EXTENSIONS
                    and not Path(path).name.startswith("._")
                    and Path(path).is_file()
                ),
                key=lambda path: str(path).casefold(),
            )
        matches = []
        for jpg_path in jpg_files:
            _check_cancelled(cancel_event)
            raw_path, status = self._find_matching_raw(raw_by_stem, jpg_path.stem)
            matches.append(
                SelectionMatch(
                    jpg_path=jpg_path,
                    raw_path=raw_path,
                    status=status,
                )
            )
        return AnalysisSummary(
            raw_source_dir=raw_source_dir,
            selected_jpg_dir=selected_jpg_dir,
            matches=matches,
        )

    def copy_matches(
        self,
        matches: list[SelectionMatch],
        work_folder: Path,
        duplicate_policy: DuplicatePolicy = "rename",
        write_xmp: bool = False,
        xmp_rating: int = 5,
        xmp_label: str = SELECTED_LABEL,
        rating_from_jpg: bool = False,
        progress_callback=None,
        cancel_event: Event | None = None,
    ) -> CopyResult:
        work_folder = Path(work_folder)
        work_folder.mkdir(parents=True, exist_ok=True)
        result = CopyResult(total=len(matches))
        copied_sources: set[str] = set()

        for index, match in enumerate(matches, start=1):
            if cancel_event is not None and cancel_event.is_set():
                result.cancelled = True
                for pending in matches[index - 1:]:
                    result.errors += 1
                    result.items.append({"path": str(pending.jpg_path), "status": "failed",
                                         "detail": "not run: cancelled"})
                result.messages.append(f"Cancelled: {len(matches) - index + 1} JPG(s) not processed")
                break
            try:
                if match.status == "ambiguous":
                    result.ambiguous += 1
                    result.messages.append(
                        f"ambiguous RAW match for {match.jpg_path.name}; skipped copy"
                    )
                    result.items.append(
                        {"path": str(match.jpg_path), "status": "ambiguous", "detail": "multiple RAW matches"}
                    )
                    continue
                if match.raw_path is None:
                    result.missing += 1
                    result.messages.append(f"missing CR3 for {match.jpg_path.name}")
                    result.items.append(
                        {"path": str(match.jpg_path), "status": "missing", "detail": "no RAW match"}
                    )
                    continue

                source_key = path_key(match.raw_path)
                if source_key in copied_sources:
                    result.skipped += 1
                    result.messages.append(
                        f"skipped {match.raw_path.name} for {match.jpg_path.name}: already copied in this run"
                    )
                    result.items.append(
                        {"path": str(match.jpg_path), "status": "skipped", "detail": "already copied in this run"}
                    )
                    continue

                effective_rating = xmp_rating
                if rating_from_jpg:
                    jpg_rating = read_jpg_rating(match.jpg_path)
                    if jpg_rating is not None:
                        effective_rating = jpg_rating

                destination_path = work_folder / match.raw_path.name
                final_path, action = self._resolve_duplicate(
                    destination_path, duplicate_policy, source_path=match.raw_path
                )
                if action == "identical":
                    # A re-run (or a retry after an XMP failure) must not clone
                    # the RAW as _001. Existing sidecars stay untouched; only a
                    # missing one is created, so a failed XMP write can recover.
                    detail = "identical copy already in work folder"
                    if write_xmp and not any(p.exists() for p in sidecar_paths_for_read(final_path)):
                        try:
                            self._write_selected_xmp(final_path, effective_rating, xmp_label)
                            result.xmp_written += 1
                            detail += "; XMP written"
                        except Exception as exc:
                            result.errors += 1
                            result.messages.append(f"{match.file_stem}: XMP write failed: {exc}")
                            result.items.append(
                                {
                                    "path": str(match.jpg_path),
                                    "status": "failed",
                                    "detail": f"RAW already at {final_path}; XMP write failed: {exc}",
                                }
                            )
                            continue
                    result.skipped += 1
                    copied_sources.add(source_key)
                    result.messages.append(f"skipped existing {final_path.name}: {detail}")
                    result.items.append({"path": str(final_path), "status": "skipped", "detail": detail})
                    continue
                if action == "skip":
                    result.skipped += 1
                    copied_sources.add(source_key)
                    result.messages.append(f"skipped existing {destination_path.name}")
                    result.items.append(
                        {"path": str(destination_path), "status": "skipped", "detail": "already exists; RAW and XMP preserved"}
                    )
                    continue
                copy_verified(match.raw_path, final_path, overwrite=action == "overwrite")
                # Only a RAW that actually reached the work folder counts, so a
                # later JPG for the same RAW still gets a try after a failure.
                copied_sources.add(source_key)
                if write_xmp:
                    try:
                        self._write_selected_xmp(final_path, effective_rating, xmp_label)
                    except Exception as exc:
                        # The RAW is in the work folder; report one failure for
                        # this JPG rather than copied + failed.
                        result.errors += 1
                        result.messages.append(f"{match.file_stem}: XMP write failed: {exc}")
                        result.items.append(
                            {
                                "path": str(match.jpg_path),
                                "status": "failed",
                                "detail": f"RAW copied to {final_path}; XMP write failed: {exc}",
                            }
                        )
                        continue
                    result.xmp_written += 1
                if action == "overwrite":
                    result.overwritten += 1
                result.copied += 1
                result.items.append({"path": str(final_path), "status": "copied"})
            except Exception as exc:  # pragma: no cover - filesystem errors vary
                result.errors += 1
                result.messages.append(f"{match.file_stem}: {exc}")
                result.items.append(
                    {"path": str(match.jpg_path), "status": "failed", "detail": str(exc)}
                )
            finally:
                if progress_callback:
                    progress_callback(index, len(matches), match.file_stem)

        return result

    @staticmethod
    def matches_for(
        matches: list[SelectionMatch], jpg_paths: list[Path]
    ) -> tuple[list[SelectionMatch], list[Path]]:
        """The matches for the given selected JPGs, in the order asked for.

        A retry uses this: it re-analyzes both folders so the RAW index is
        current, then narrows the run to the JPGs that went wrong last time.
        JPGs the analysis no longer lists come back separately so the caller
        can record them instead of letting them vanish.
        """
        by_path = {path_key(match.jpg_path): match for match in matches}
        found: list[SelectionMatch] = []
        missing: list[Path] = []
        for path in jpg_paths:
            match = by_path.get(path_key(path))
            if match is None:
                missing.append(path)
            else:
                found.append(match)
        return found, missing

    @staticmethod
    def note_missing(result: CopyResult, jpg_paths: list[Path], detail: str) -> None:
        """Record JPGs a run could not reach, in the same shape copy_matches uses."""
        for path in jpg_paths:
            result.total += 1
            result.missing += 1
            result.messages.append(f"{path.name}: {detail}")
            result.items.append({"path": str(path), "status": "missing", "detail": detail})

    @staticmethod
    def _index_cr3_files(root: Path, recursive: bool, exclude: Path | None = None,
                         cancel_event: Event | None = None) -> dict[str, list[Path]]:
        files = _walk_files(root, recursive, exclude=exclude, cancel_event=cancel_event)
        raw_files = sorted(
            (
                path
                for path in files
                if path.suffix.casefold() in RAW_EXTENSIONS
                and not path.name.startswith("._")
                and path.is_file()
            ),
            key=lambda path: (path.stem.casefold(), len(path.parts), str(path).casefold()),
        )
        index: dict[str, list[Path]] = {}
        for path in raw_files:
            _check_cancelled(cancel_event)
            for key in AutoSelectorService._match_keys(path.stem, anchored=True):
                bucket = index.setdefault(key, [])
                if path not in bucket:
                    bucket.append(path)
        return index

    @staticmethod
    def _find_matching_raw(
        raw_by_stem: dict[str, list[Path]], jpg_stem: str
    ) -> tuple[Path | None, str]:
        stem_key = jpg_stem.casefold()
        # The exact file name wins over any camera-ID overlap.
        exact = [path for path in raw_by_stem.get(stem_key, ()) if path.stem.casefold() == stem_key]
        if exact:
            return (exact[0], "matched") if len(exact) == 1 else (None, "ambiguous")
        candidates: list[Path] = []
        for key in AutoSelectorService._match_keys(jpg_stem):
            if key == stem_key:
                continue
            for path in raw_by_stem.get(key, ()):
                if path not in candidates:
                    candidates.append(path)
        if len(candidates) == 1:
            return candidates[0], "matched"
        if len(candidates) > 1:
            return None, "ambiguous"
        return None, "missing"

    @staticmethod
    def _match_keys(stem: str, anchored: bool = False) -> list[str]:
        """Lookup keys for a file stem: the stem, plus camera IDs inside it.

        ``anchored`` (RAW side) keeps only IDs at the start of the stem, so a
        RAW named ``Trip_IMG_1234`` is not claimed by ``IMG_1234.jpg``.
        """
        keys = [stem.casefold()]
        for pattern in CAMERA_ID_PATTERNS:
            for match in pattern.finditer(stem):
                if anchored and match.start() != 0:
                    continue
                keys.append(match.group(0).casefold())
        return list(dict.fromkeys(keys))

    @staticmethod
    def _list_jpg_files(root: Path, recursive: bool, cancel_event: Event | None = None) -> list[Path]:
        files = _walk_files(root, recursive, skip_cache=True, cancel_event=cancel_event)
        return sorted(
            (
                path
                for path in files
                if path.suffix.casefold() in JPG_EXTENSIONS
                and not path.name.startswith("._")
                and CACHE_DIR_NAME not in path.relative_to(root).parts
                and path.is_file()
            ),
            key=lambda path: str(path).casefold(),
        )

    @staticmethod
    def _resolve_duplicate(destination_path: Path, duplicate_policy: DuplicatePolicy,
                           source_path: Path | None = None) -> tuple[Path, str]:
        if not destination_path.exists():
            return destination_path, "copy"
        if duplicate_policy == "skip":
            return destination_path, "skip"
        if duplicate_policy == "overwrite":
            return destination_path, "overwrite"

        if source_path is not None and _identical_files(source_path, destination_path):
            return destination_path, "identical"

        stem = destination_path.stem
        suffix = destination_path.suffix
        # Check existing renamed copies even when an earlier numbered file was
        # removed. A retry after XMP failure must find the RAW already copied.
        pattern = re.compile(rf"{re.escape(stem)}_(\d{{3,4}}){re.escape(suffix)}", re.IGNORECASE)
        occupied: set[int] = set()
        for candidate in sorted(destination_path.parent.iterdir(), key=lambda path: path.name.casefold()):
            match = pattern.fullmatch(candidate.name)
            if match is None:
                continue
            number = int(match.group(1))
            occupied.add(number)
            if source_path is not None and _identical_files(source_path, candidate):
                return candidate, "identical"
        for index in range(1, 10000):
            candidate = destination_path.with_name(f"{stem}_{index:03d}{suffix}")
            if index not in occupied and not candidate.exists():
                return candidate, "copy"
        raise RuntimeError(f"Could not resolve duplicate name for {destination_path}")

    @staticmethod
    def _require_dir(path: Path, label: str) -> None:
        if not path.exists():
            raise FileNotFoundError(f"{label} does not exist: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"{label} is not a folder: {path}")

    @staticmethod
    def _write_selected_xmp(raw_path: Path, rating: int, label: str) -> None:
        label = label.strip() or SELECTED_LABEL
        write_xmp_sidecar(raw_path, rating=rating, label=label, keywords=(label,))
