from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.branding import NDEX_AUTO_SELECTOR_TITLE

from ndex_auto_selector.ndex_auto_selector.services.selector import AutoSelectorService
from ndex_auto_selector.ndex_auto_selector.ui.tk_app import run_app
from ndex_common.crashlog import install_crash_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=NDEX_AUTO_SELECTOR_TITLE)
    parser.add_argument(
        "--raw-source",
        type=Path,
        help="Folder containing original RAW files (CR3/CR2/ARW/SRF/SR2/NEF/NRW)",
    )
    parser.add_argument("--selected-jpg", type=Path, help="Folder containing selected JPG files")
    parser.add_argument("--work-folder", type=Path, help="Destination folder for matched CR3 copies")
    parser.add_argument("--recursive", action="store_true", default=True, help="Scan source folders recursively")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false")
    parser.add_argument("--analyze", action="store_true", help="Analyze matches and print a summary")
    parser.add_argument("--copy", action="store_true", help="Copy matched CR3 files into the work folder")
    parser.add_argument("--write-xmp", action="store_true", help="Write XMP sidecars for selected CR3 files")
    parser.add_argument("--xmp-rating", type=int, choices=range(0, 6), default=5, help="XMP star rating from 0 to 5")
    parser.add_argument("--xmp-label", default="NDEX Selected", help="XMP label and keyword for selected files")
    parser.add_argument(
        "--xmp-rating-from-jpg",
        action="store_true",
        help=(
            "Read the star rating from each selected JPG (sidecar, EXIF, or embedded XMP) "
            "and copy it to the CR3 XMP. Falls back to --xmp-rating when none is found."
        ),
    )
    parser.add_argument(
        "--duplicate-policy",
        choices=["rename", "skip", "overwrite"],
        default="rename",
        help="How to handle CR3 files that already exist in the work folder",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the GUI with folder arguments preloaded (used by NDEX handoff)",
    )
    return parser


def main() -> int:
    install_crash_logging("NDEX Auto Selector")
    args = build_parser().parse_args()

    if args.open:
        run_app(
            initial_raw_source=args.raw_source,
            initial_selected_jpg=args.selected_jpg,
            initial_work_folder=args.work_folder,
        )
        return 0

    cli_mode = any([args.raw_source, args.selected_jpg, args.work_folder, args.analyze, args.copy])

    if not cli_mode:
        run_app()
        return 0

    if not args.raw_source or not args.selected_jpg:
        raise SystemExit("--raw-source and --selected-jpg are required for CLI mode.")
    if args.copy and not args.work_folder:
        raise SystemExit("--work-folder is required with --copy.")

    service = AutoSelectorService()
    summary = service.analyze(args.raw_source, args.selected_jpg, recursive=args.recursive)
    _emit(f"CR3 source: {summary.raw_source_dir}")
    _emit(f"Selected JPG folder: {summary.selected_jpg_dir}")
    _emit(f"Selected JPG: {summary.selected_count}")
    _emit(f"Matched CR3: {summary.matched_count}")
    _emit(f"Missing CR3: {summary.missing_count}")

    if args.copy:
        result = service.copy_matches(
            summary.matches,
            args.work_folder,
            args.duplicate_policy,
            write_xmp=args.write_xmp,
            xmp_rating=args.xmp_rating,
            xmp_label=args.xmp_label,
            rating_from_jpg=args.xmp_rating_from_jpg,
        )
        _emit(
            "Copy result: "
            f"copied={result.copied}, xmp={result.xmp_written}, skipped={result.skipped}, "
            f"overwritten={result.overwritten}, missing={result.missing}, errors={result.errors}"
        )
        for message in result.messages:
            _emit(message)

    return 0


def _emit(message: str) -> None:
    if sys.stdout is not None:
        print(message)


if __name__ == "__main__":
    raise SystemExit(main())
