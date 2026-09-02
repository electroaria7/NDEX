from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.branding import NDEX_IMAGE_MANAGER_TITLE
from dsb_image_manager.dsb_image_manager.services.backup import BackupService
from dsb_image_manager.dsb_image_manager.services.scanner import ImageScanner
from dsb_image_manager.dsb_image_manager.services.xmp_export import XmpExportService
from dsb_image_manager.dsb_image_manager.ui.tk_app import run_app
from ndex_common.crashlog import install_crash_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=NDEX_IMAGE_MANAGER_TITLE)
    parser.add_argument("--source", type=Path, help="Folder to scan")
    parser.add_argument("--recursive", action="store_true", default=True, help="Scan subfolders")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false")
    parser.add_argument("--scan", action="store_true", help="Scan source and print a summary")
    parser.add_argument("--backup-destination", type=Path, help="Destination root for NDEX backups")
    parser.add_argument(
        "--backup-picked",
        action="store_true",
        help="Back up Pick-rated files after scanning",
    )
    parser.add_argument(
        "--duplicate-policy",
        choices=["rename", "skip", "overwrite"],
        default="rename",
        help="How to handle files that already exist at the destination",
    )
    parser.add_argument(
        "--export-xmp",
        action="store_true",
        help=(
            "Write .xmp sidecars next to originals for picked/rated images "
            "(readable by Auto Selector, Lightroom, and Evoto)"
        ),
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the GUI with --source preloaded (used by NDEX handoff)",
    )
    return parser


def main() -> int:
    install_crash_logging("NDEX Image Manager")
    args = build_parser().parse_args()

    if args.open:
        run_app(initial_source=args.source)
        return 0

    if args.source or args.scan or args.backup_picked or args.export_xmp:
        if not args.source:
            raise SystemExit("--source is required for CLI scan/backup mode.")

        scanner = ImageScanner()
        result = scanner.scan(args.source, recursive=args.recursive)
        _emit(f"Scanned: {result.source_dir}")
        _emit(f"Images: {result.total}")
        _emit(f"JPG: {result.jpg_count} / RAW: {result.raw_count}")
        _emit(f"Pairs: {result.pair_count}")
        _emit(f"Catalog: {result.catalog_path}")

        if args.backup_picked:
            if not args.backup_destination:
                raise SystemExit("--backup-destination is required with --backup-picked.")
            records = [record for record in result.records if record.pick_status == "Pick"]
            backup = BackupService().backup(records, args.backup_destination, args.duplicate_policy)
            _emit(
                "Backup: "
                f"copied={backup.copied}, skipped={backup.skipped}, "
                f"overwritten={backup.overwritten}, errors={backup.errors}"
            )
            from ndex_common.workflow import record_job

            record_job(
                app="image_manager",
                type="backup",
                source=str(args.source),
                destination=str(args.backup_destination),
                counts={
                    "copied": backup.copied,
                    "skipped": backup.skipped,
                    "failed": backup.errors,
                    "overwritten": backup.overwritten,
                },
                items=[
                    {"path": "", "status": "message", "detail": message}
                    for message in backup.messages[:50]
                ],
                folders={"source": str(args.source)},
            )

        if args.export_xmp:
            xmp_summary = XmpExportService().export(result.records)
            _emit(
                "XMP export: "
                f"written={xmp_summary.written}, skipped={xmp_summary.skipped}, "
                f"errors={xmp_summary.errors}"
            )
            for message in xmp_summary.messages:
                _emit(f"  {message}")
        return 0

    run_app()
    return 0


def _emit(message: str) -> None:
    if sys.stdout is not None:
        print(message)


if __name__ == "__main__":
    raise SystemExit(main())
