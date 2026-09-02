from __future__ import annotations

import hashlib
import os
import shutil
import threading
from pathlib import Path

TEMP_SUFFIX = ".ndex_tmp"

from .folder_manager import resolve_duplicate_path
from .models import BackupResult, DuplicatePolicy, ScanItem, VerifyMode


def execute_backup(
    items: list[ScanItem],
    duplicate_policy: DuplicatePolicy = "rename",
    dry_run: bool = False,
    verify_mode: VerifyMode = "size",
    progress_callback=None,
    logger=None,
    cancel_event: threading.Event | None = None,
) -> BackupResult:
    result = BackupResult(total=len(items), dry_run=dry_run)

    ordered_items = sorted(items, key=lambda item: (item.capture_datetime, str(item.source_path).lower()))

    for index, item in enumerate(ordered_items, start=1):
        if cancel_event and cancel_event.is_set():
            result.cancelled = True
            if logger:
                logger.warn("Backup cancelled by user")
            break

        destination_dir = item.destination_dir
        destination_path = destination_dir / item.source_path.name

        try:
            final_path, action = _resolve_destination(
                destination_path, duplicate_policy, item.source_path
            )
            if action == "skip":
                result.skipped += 1
                _record(result, item, final_path, "skipped", "already exists")
                if logger:
                    logger.skip(f"{item.source_path.name} already exists")
            elif action == "skip_identical":
                result.skipped += 1
                _record(
                    result,
                    item,
                    final_path,
                    "skipped",
                    f"identical file already backed up as {final_path.name}",
                )
                if logger:
                    logger.skip(
                        f"{item.source_path.name} identical file already backed up "
                        f"as {final_path.name}"
                    )
            else:
                overwriting_existing = destination_path.exists() and duplicate_policy == "overwrite"

                if dry_run:
                    result.copied += 1
                    if overwriting_existing:
                        result.overwritten += 1
                    _record(result, item, final_path, "planned")
                    if logger:
                        logger.info(
                            f"[DRY RUN] {item.source_path.name} -> {final_path.parent.as_posix()}"
                        )
                else:
                    destination_dir.mkdir(parents=True, exist_ok=True)
                    temp_path = final_path.parent / f".{final_path.name}{TEMP_SUFFIX}"
                    try:
                        shutil.copy2(item.source_path, temp_path)
                        verified = verify_mode == "none" or _verify_copy(
                            item.source_path, temp_path, verify_mode
                        )
                        if verified:
                            os.replace(temp_path, final_path)
                            result.copied += 1
                            if overwriting_existing:
                                result.overwritten += 1
                            _record(result, item, final_path, "copied")
                            if logger:
                                logger.ok(
                                    f"copied {item.source_path.name} -> {final_path.parent.as_posix()}"
                                )
                            if verify_mode != "none":
                                result.verified += 1
                                if logger:
                                    logger.ok(f"verified {item.source_path.name} ({verify_mode})")
                        else:
                            result.verification_failed += 1
                            result.errors += 1
                            message = (
                                f"{item.source_path.name} verification failed "
                                f"after copy ({verify_mode}); existing backup left untouched"
                            )
                            result.messages.append(message)
                            _record(
                                result,
                                item,
                                final_path,
                                "failed",
                                f"verification failed ({verify_mode})",
                            )
                            if logger:
                                logger.error(message)
                    finally:
                        if temp_path.exists():
                            try:
                                temp_path.unlink()
                            except OSError:
                                if logger:
                                    logger.warn(f"could not remove temp file {temp_path.name}")
        except Exception as exc:  # pragma: no cover - filesystem failures vary by OS
            result.errors += 1
            message = f"{item.source_path.name} failed: {exc}"
            result.messages.append(message)
            _record(result, item, destination_path, "failed", str(exc))
            if logger:
                logger.error(message)

        if progress_callback:
            progress_callback("backup", index, len(ordered_items), item.source_path.name)

    if logger and not result.cancelled:
        if dry_run:
            logger.info("Dry run completed")
        else:
            logger.info("Backup completed")
    return result


def _record(
    result: BackupResult,
    item: ScanItem,
    destination: Path,
    status: str,
    detail: str = "",
) -> None:
    """Note what happened to one file, keyed by its source path.

    The source path is what a retry needs: it is the file to copy again, and
    it is still meaningful when the destination was never written.
    """
    result.items.append(
        {
            "path": str(item.source_path),
            "status": status,
            "detail": detail,
            "destination": str(destination),
        }
    )


def _resolve_destination(
    destination_path: Path,
    duplicate_policy: DuplicatePolicy,
    source_path: Path | None = None,
) -> tuple[Path, str]:
    if not destination_path.exists():
        return destination_path, "copy"

    if duplicate_policy == "skip":
        return destination_path, "skip"
    if duplicate_policy == "overwrite":
        return destination_path, "copy"
    if duplicate_policy == "smart" and source_path is not None:
        identical = _find_identical_existing(destination_path, source_path)
        if identical is not None:
            return identical, "skip_identical"
    return resolve_duplicate_path(destination_path), "copy"


def _find_identical_existing(destination_path: Path, source_path: Path) -> Path | None:
    source_size = source_path.stat().st_size
    source_hash: str | None = None

    stem = destination_path.stem
    suffix = destination_path.suffix
    candidates = [destination_path]
    candidates.extend(sorted(destination_path.parent.glob(f"{stem}_[0-9][0-9][0-9]{suffix}")))

    for candidate in candidates:
        if not candidate.is_file():
            continue
        if candidate.stat().st_size != source_size:
            continue
        if source_hash is None:
            source_hash = _sha256(source_path)
        if _sha256(candidate) == source_hash:
            return candidate
    return None


def _verify_copy(source_path: Path, destination_path: Path, verify_mode: VerifyMode) -> bool:
    if not destination_path.exists():
        return False

    if source_path.stat().st_size != destination_path.stat().st_size:
        return False

    if verify_mode == "size":
        return True

    if verify_mode == "sha256":
        return _sha256(source_path) == _sha256(destination_path)

    return True


def _sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
