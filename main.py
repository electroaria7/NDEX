from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.app_paths import get_user_data_dir
from src.backup_executor import execute_backup
from src.branding import NDEX_ONE_TITLE
from src.config import ConfigManager
from src.file_types import FILE_TYPE_ORDER, get_file_type_definitions, get_visible_file_types
from src.gui import run_app
from src.logger import AppLogger
from src.metadata import MetadataExtractor
from src.scanner import analyze_source

from ndex_common.crashlog import install_crash_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{NDEX_ONE_TITLE} - Data Sort Backup")
    parser.add_argument("--source", type=Path, help="Source folder to scan")
    parser.add_argument("--destination", type=Path, help="Backup destination root")
    parser.add_argument(
        "--duplicate-policy",
        choices=["rename", "skip", "overwrite", "smart"],
        default="rename",
        help=(
            "How to handle duplicate filenames. "
            "'smart' skips files whose content (SHA-256) already exists at the destination "
            "and renames when content differs."
        ),
    )
    parser.add_argument(
        "--type",
        dest="enabled_types",
        action="append",
        choices=FILE_TYPE_ORDER,
        help="File type to include. Repeat to include multiple types.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not copy")
    parser.add_argument(
        "--verify-mode",
        choices=["none", "size", "sha256"],
        default=None,
        help="Copy verification mode. Default comes from settings.",
    )
    parser.add_argument("--analyze", action="store_true", help="Analyze files and print a summary")
    parser.add_argument("--backup", action="store_true", help="Run the backup after analysis")
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the GUI with folder arguments preloaded (used by NDEX handoff)",
    )
    return parser


def print_summary(summary) -> None:
    if sys.stdout is None:
        return
    counts = summary.counts
    total = sum(counts.values())
    print(f"Source: {summary.source_dir}")
    print(f"Destination: {summary.backup_root}")
    print(f"Total files: {total}")
    print(f"Files: {_format_type_counts(counts)}")
    if summary.date_range[0] and summary.date_range[1]:
        start = summary.date_range[0].strftime("%Y-%m-%d")
        end = summary.date_range[1].strftime("%Y-%m-%d")
        print(f"Date range: {start} ~ {end}")
    print("")
    print("Folder preview:")
    for row in summary.preview_rows:
        print(
            f"  {row.folder_rel_path.as_posix()} | "
            f"{_format_type_counts(row.type_counts)} | {row.status}"
        )


def run_cli(args: argparse.Namespace) -> int:
    if not args.source or not args.destination:
        raise SystemExit("--source and --destination are required for CLI mode.")

    root_dir = get_user_data_dir()
    config = ConfigManager()
    settings = config.load()

    visible_types = get_visible_file_types(settings.get("raw_brands", {}))
    enabled_types = args.enabled_types or [
        key
        for key in visible_types
        if settings["default_file_types"].get(key, False)
    ]

    logger = AppLogger(sink=lambda line: print(line) if sys.stdout is not None else None)
    extractor = MetadataExtractor.from_settings(settings)

    summary = analyze_source(
        source_dir=args.source,
        backup_root=args.destination,
        metadata_extractor=extractor,
        enabled_types=enabled_types,
        logger=logger,
    )
    print_summary(summary)

    if args.backup:
        result = execute_backup(
            items=summary.items,
            duplicate_policy=args.duplicate_policy,
            dry_run=args.dry_run,
            verify_mode=args.verify_mode or settings.get("verify_mode", "size"),
            logger=logger,
        )
        if sys.stdout is not None:
            print("")
            print(
                "Backup result: "
                f"copied={result.copied}, verified={result.verified}, "
                f"verification_failed={result.verification_failed}, skipped={result.skipped}, "
                f"overwritten={result.overwritten}, errors={result.errors}, "
                f"cancelled={result.cancelled}"
            )
        if not result.dry_run:
            from ndex_common.workflow import record_backup

            record_backup(args.source, args.destination, result)
    return 0


def _format_type_counts(counts: dict[str, int]) -> str:
    definitions = get_file_type_definitions()
    parts = []
    for file_type in FILE_TYPE_ORDER:
        count = counts.get(file_type, 0)
        if count:
            label = "JPG" if file_type == "jpg" else definitions[file_type]["label"].split(" ")[-1]
            parts.append(f"{label}: {count}")
    return " / ".join(parts) if parts else "None"


def main() -> int:
    install_crash_logging("NDEX One")
    parser = build_parser()
    args = parser.parse_args()

    if args.open:
        run_app(
            initial_source=args.source,
            initial_destination=args.destination,
            preload_only=True,
        )
        return 0

    cli_mode = any(
        [
            args.source,
            args.destination,
            args.analyze,
            args.backup,
            args.dry_run,
            args.verify_mode,
            args.enabled_types,
        ]
    )
    if cli_mode:
        return run_cli(args)

    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
