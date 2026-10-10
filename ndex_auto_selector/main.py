from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.branding import NDEX_AUTO_SELECTOR_TITLE

from ndex_auto_selector.ndex_auto_selector.services.selector import AutoSelectorService, load_handoff
from ndex_auto_selector.ndex_auto_selector.ui.tk_app import run_app
from ndex_common.crashlog import install_crash_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=NDEX_AUTO_SELECTOR_TITLE)
    parser.add_argument(
        "--raw-source",
        type=Path,
        help="Folder containing original RAW files (CR3, CR2, ARW, SRF, SR2, NEF, NRW)",
    )
    parser.add_argument("--selected-jpg", type=Path, help="Folder containing selected JPG files")
    parser.add_argument("--work-folder", type=Path, help="Destination folder for matched RAW copies")
    parser.add_argument("--recursive", action="store_true", default=True, help="Scan source folders recursively")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false")
    parser.add_argument("--analyze", action="store_true", help="Analyze matches and print a summary")
    parser.add_argument("--copy", action="store_true", help="Copy matched RAW files into the work folder")
    parser.add_argument("--write-xmp", action="store_true", help="Write XMP sidecars for copied RAW files")
    parser.add_argument("--xmp-rating", type=int, choices=range(0, 6), default=5, help="XMP star rating from 0 to 5")
    parser.add_argument("--xmp-label", default="NDEX Selected", help="XMP label and keyword for selected files")
    parser.add_argument(
        "--xmp-rating-from-jpg",
        action="store_true",
        help=(
            "Read the star rating from each selected JPG (sidecar, EXIF, or embedded XMP) "
            "and copy it to the RAW XMP. Falls back to --xmp-rating when none is found."
        ),
    )
    parser.add_argument(
        "--duplicate-policy",
        choices=["rename", "skip", "overwrite"],
        default="rename",
        help="How to handle RAW files that already exist in the work folder",
    )
    parser.add_argument(
        "--handoff",
        type=Path,
        help="Select-handoff manifest from Image Manager: only its picked JPGs are matched.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the GUI with folder arguments preloaded (used by NDEX handoff)",
    )
    parser.add_argument(
        "--retry",
        type=Path,
        help="Open Job Results at this extract manifest so its failed files can be retried.",
    )
    return parser


def main() -> int:
    install_crash_logging("NDEX Auto Selector")
    args = build_parser().parse_args()

    if args.open or args.retry is not None:
        run_app(
            initial_raw_source=args.raw_source,
            initial_selected_jpg=args.selected_jpg,
            initial_work_folder=args.work_folder,
            retry_manifest=args.retry,
            initial_handoff=args.handoff,
        )
        return 0

    cli_mode = any(
        [args.raw_source, args.selected_jpg, args.handoff, args.work_folder, args.analyze, args.copy]
    )

    if not cli_mode:
        run_app()
        return 0

    selected_jpg = args.selected_jpg
    jpg_files = None
    if args.handoff is not None:
        try:
            handoff_source, jpg_files = load_handoff(args.handoff)
        except ValueError as exc:
            raise SystemExit(str(exc))
        selected_jpg = handoff_source or (jpg_files[0].parent if jpg_files else None)
    if not args.raw_source or not selected_jpg:
        raise SystemExit("--raw-source and --selected-jpg (or --handoff) are required for CLI mode.")
    if args.copy and not args.work_folder:
        raise SystemExit("--work-folder is required with --copy.")

    service = AutoSelectorService()
    summary = service.analyze(
        args.raw_source,
        selected_jpg,
        recursive=args.recursive,
        exclude=args.work_folder,
        jpg_files=jpg_files,
    )
    _emit(f"RAW folder: {summary.raw_source_dir}")
    _emit(f"Selected JPGs folder: {summary.selected_jpg_dir}")
    _emit(f"Selected JPG: {summary.selected_count}")
    _emit(f"Matched RAW: {summary.matched_count}")
    _emit(f"No RAW found: {summary.missing_count}")
    _emit(f"Ambiguous: {summary.ambiguous_count}")

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
        from ndex_common.workflow import record_extract

        record_extract(
            selected_jpg, args.raw_source, args.work_folder, result, recursive=args.recursive
        )
        if result.errors > 0:
            return 1

    return 0


def _emit(message: str) -> None:
    if sys.stdout is not None:
        print(message)


if __name__ == "__main__":
    raise SystemExit(main())
