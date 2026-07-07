from __future__ import annotations

import shutil
import re
from pathlib import Path

from ndex_common.rating import read_jpg_rating
from ndex_common.xmp import write_xmp_sidecar

from ..core.models import AnalysisSummary, CopyResult, DuplicatePolicy, SelectionMatch

JPG_EXTENSIONS = {".jpg", ".jpeg"}
RAW_EXTENSIONS = {".cr3", ".cr2", ".arw", ".srf", ".sr2", ".nef", ".nrw"}
CAMERA_ID_PATTERNS = (
    re.compile(r"IMG_\d{4}", re.IGNORECASE),   # Canon: IMG_0001
    re.compile(r"_DSC\d{4}", re.IGNORECASE),   # Nikon (Adobe RGB): _DSC0001
    re.compile(r"DSC_\d{4}", re.IGNORECASE),   # Nikon (sRGB): DSC_0001
    re.compile(r"DSC\d{5}", re.IGNORECASE),    # Sony: DSC00001
)
SELECTED_LABEL = "NDEX Selected"


class AutoSelectorService:
    def analyze(
        self,
        raw_source_dir: Path,
        selected_jpg_dir: Path,
        recursive: bool = True,
    ) -> AnalysisSummary:
        raw_source_dir = Path(raw_source_dir)
        selected_jpg_dir = Path(selected_jpg_dir)
        self._require_dir(raw_source_dir, "CR3 source folder")
        self._require_dir(selected_jpg_dir, "selected JPG folder")

        raw_by_stem = self._index_cr3_files(raw_source_dir, recursive=recursive)
        jpg_files = self._list_jpg_files(selected_jpg_dir, recursive=recursive)
        matches = []
        for jpg_path in jpg_files:
            raw_path = self._find_matching_raw(raw_by_stem, jpg_path.stem)
            matches.append(
                SelectionMatch(
                    jpg_path=jpg_path,
                    raw_path=raw_path,
                    status="matched" if raw_path else "missing",
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
    ) -> CopyResult:
        work_folder = Path(work_folder)
        work_folder.mkdir(parents=True, exist_ok=True)
        result = CopyResult(total=len(matches))

        for index, match in enumerate(matches, start=1):
            try:
                if match.raw_path is None:
                    result.missing += 1
                    result.messages.append(f"missing CR3 for {match.jpg_path.name}")
                    continue

                effective_rating = xmp_rating
                if rating_from_jpg:
                    jpg_rating = read_jpg_rating(match.jpg_path)
                    if jpg_rating is not None:
                        effective_rating = jpg_rating

                destination_path = work_folder / match.raw_path.name
                final_path, action = self._resolve_duplicate(destination_path, duplicate_policy)
                if action == "skip":
                    if write_xmp:
                        self._write_selected_xmp(destination_path, effective_rating, xmp_label)
                        result.xmp_written += 1
                    result.skipped += 1
                    result.messages.append(f"skipped existing {destination_path.name}")
                    continue
                if action == "overwrite":
                    result.overwritten += 1

                shutil.copy2(match.raw_path, final_path)
                result.copied += 1
                if write_xmp:
                    self._write_selected_xmp(final_path, effective_rating, xmp_label)
                    result.xmp_written += 1
            except Exception as exc:  # pragma: no cover - filesystem errors vary
                result.errors += 1
                result.messages.append(f"{match.file_stem}: {exc}")
            finally:
                if progress_callback:
                    progress_callback(index, len(matches), match.file_stem)

        return result

    @staticmethod
    def _index_cr3_files(root: Path, recursive: bool) -> dict[str, Path]:
        files = root.rglob("*") if recursive else root.glob("*")
        raw_files = sorted(
            (path for path in files if path.is_file() and path.suffix.casefold() in RAW_EXTENSIONS),
            key=lambda path: (path.stem.casefold(), len(path.parts), str(path).casefold()),
        )
        index: dict[str, Path] = {}
        for path in raw_files:
            for key in AutoSelectorService._match_keys(path.stem):
                index.setdefault(key, path)
        return index

    @staticmethod
    def _find_matching_raw(raw_by_stem: dict[str, Path], jpg_stem: str) -> Path | None:
        for key in AutoSelectorService._match_keys(jpg_stem):
            raw_path = raw_by_stem.get(key)
            if raw_path:
                return raw_path
        return None

    @staticmethod
    def _match_keys(stem: str) -> list[str]:
        keys = [stem.casefold()]
        for pattern in CAMERA_ID_PATTERNS:
            keys.extend(match.group(0).casefold() for match in pattern.finditer(stem))
        return list(dict.fromkeys(keys))

    @staticmethod
    def _list_jpg_files(root: Path, recursive: bool) -> list[Path]:
        files = root.rglob("*") if recursive else root.glob("*")
        return sorted(
            (path for path in files if path.is_file() and path.suffix.casefold() in JPG_EXTENSIONS),
            key=lambda path: str(path).casefold(),
        )

    @staticmethod
    def _resolve_duplicate(destination_path: Path, duplicate_policy: DuplicatePolicy) -> tuple[Path, str]:
        if not destination_path.exists():
            return destination_path, "copy"
        if duplicate_policy == "skip":
            return destination_path, "skip"
        if duplicate_policy == "overwrite":
            return destination_path, "overwrite"

        stem = destination_path.stem
        suffix = destination_path.suffix
        for index in range(1, 10000):
            candidate = destination_path.with_name(f"{stem}_{index:03d}{suffix}")
            if not candidate.exists():
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
