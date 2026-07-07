# DSB Improvement Review

Date: 2026-05-08

## Review Summary

The current DSB MVP has the right core direction: scan first, preview folders, copy without modifying source files, and verify copied files. The next improvement pass should focus on making backup operations more failure-resistant, making metadata analysis feel faster and more transparent, and keeping packaged releases clean.

Recommended priority:

1. Make file copy atomic and verification-aware.
2. Improve metadata batch handling for large folders.
3. Add clearer progress states for analysis and verification.
4. Clean up packaging and release artifacts.
5. Expand tests around failure cases and real-world camera folders.

## Priority 1: Safer Copy Flow

Current area:

- `src/backup_executor.py`

Issue:

DSB currently copies directly to the final destination path with `shutil.copy2()`, then verifies the result. If the app is cancelled, the drive disconnects, or the PC sleeps during copy, a partial or corrupted file could remain at the final path. A later run may treat that file as an existing duplicate.

Recommended change:

- Copy to a temporary file in the destination folder first.
- Verify the temporary file.
- Rename or replace it into the final filename only after verification passes.
- If verification fails, keep or delete the temporary file according to a clear policy and log the reason.

Suggested flow:

```text
source.CR3
  -> destination/.source.CR3.dsb_tmp
  -> verify temp file
  -> destination/source.CR3
```

For overwrite mode, do not overwrite the existing backup until the new temporary copy has passed verification.

Expected benefit:

- Avoids partial files being mistaken for valid backups.
- Makes cancel/retry behavior much safer.
- Protects existing backups during overwrite operations.

## Priority 2: Metadata Analysis Performance

Current area:

- `src/metadata.py`
- `src/scanner.py`

Issue:

Metadata reading is now batched, which is a strong improvement. However, each ExifTool chunk has a fixed timeout of 10 seconds for up to 200 files. On slow SD cards, network drives, or large CR3 sets, a chunk may time out and cause many files to fall back to modified time even though ExifTool could have read them with more time.

Recommended change:

- Make ExifTool chunk size and timeout configurable.
- Retry timed-out chunks with smaller chunk sizes.
- Log batch-level failures with counts, not only per-file fallback warnings.
- Consider reading JPG/JPEG with Pillow first and using ExifTool mainly for CR3, depending on real-world speed tests.

Suggested settings:

```json
{
  "metadata_batch_size": 100,
  "metadata_batch_timeout_seconds": 60,
  "retry_failed_metadata_batches": true
}
```

Expected benefit:

- Better performance on normal folders.
- More reliable capture dates on slow media.
- Fewer unnecessary modified-time fallbacks.

## Priority 3: Analysis Progress Feedback

Current area:

- `src/scanner.py`
- `src/gui.py`

Issue:

The GUI progress bar updates while iterating over analyzed files, but the expensive metadata batch read happens before those per-file progress callbacks. On large folders, the app may look idle during the metadata phase.

Recommended change:

- Split analysis progress into clear stages:
  - Scanning files
  - Reading metadata
  - Building preview
- Add progress callbacks inside metadata batch processing.
- Show current stage in the status label and log.

Suggested status examples:

```text
Scanning files...
Reading metadata batch 3 / 18...
Building preview...
Analysis completed.
```

Expected benefit:

- The app feels responsive even during long scans.
- Users can distinguish a slow operation from a frozen app.

## Priority 4: Verification UX

Current area:

- `src/gui.py`
- `src/backup_executor.py`
- `src/models.py`

Issue:

Copy verification exists, but the UI only exposes the mode as `size`, `sha256`, or `none`. That is functional, but a non-technical user may not know when to choose each option.

Recommended change:

- Rename UI labels to clearer text:
  - `Fast check (file size)`
  - `Full check (SHA-256, slower)`
  - `No verification`
- Show copied, verified, failed, skipped, and error counts in a compact result section after backup.
- Add a separate log level or summary line for verification failures.

Expected benefit:

- Safer defaults remain easy to understand.
- Users can make informed speed vs. certainty choices.

## Priority 5: Duplicate Detection Beyond Filename

Current area:

- `src/folder_manager.py`
- `src/backup_executor.py`

Issue:

Duplicate handling is currently filename-based. Camera filenames repeat across cards and sessions, so rename mode protects data but can create multiple identical copies if the same card is backed up twice.

Recommended change:

- Add optional hash-based duplicate detection.
- Keep filename-based rename as the default safe behavior.
- Add a stronger mode later:

```text
If same filename and same hash exists: skip as already backed up.
If same filename but different hash exists: rename.
```

Expected benefit:

- Avoids repeated backups of identical files.
- Preserves safety when filenames collide but content differs.

## Priority 6: Packaging Hygiene

Current area:

- `build/`
- `dist/`
- `vendor/`
- temporary test folders

Issue:

Build output, `__pycache__`, temporary test folders, and packaged binaries are mixed into the project folder. That is workable locally, but it makes review, backup, and future source control noisy.

Recommended change:

- Add a `.gitignore`.
- Add a cleanup script for generated artifacts.
- Keep source files separate from release output.
- Add a `releases/` or `artifacts/` folder for final distributables only.

Suggested ignored paths:

```text
__pycache__/
*.pyc
build/DSB/
build/DSB.onefile/
dist/
.build_tools/
.dsb_data/
tmp_*/
```

Expected benefit:

- Cleaner project folder.
- Easier version control.
- Less chance of accidentally distributing test files.

## Priority 7: Installer Completion

Current area:

- `build/installer.iss`
- `build/build.ps1`

Issue:

The installer script exists, but the installer build depends on Inno Setup being installed locally. That part has not been fully verified in this environment.

Recommended change:

- Install Inno Setup and run the installer build once end-to-end.
- Add installer output checks.
- Add ExifTool license text to installer or bundled documentation.
- Decide whether the main distribution should be:
  - single EXE,
  - portable folder,
  - installer.

Recommended default:

Use the portable folder or installer for regular distribution. Keep the single EXE for convenience, but note that one-file startup can be slower because it extracts bundled files at launch.

## Priority 8: Better Test Coverage

Current area:

- `tests/`

Current coverage is useful but still mostly happy-path focused.

Recommended new tests:

- Verification failure increments `verification_failed` and `errors`.
- Existing file with `skip` policy does not copy or verify.
- Existing file with `overwrite` policy preserves old file if temp-copy verification fails.
- Metadata batch timeout falls back predictably.
- Preview reports `Existing`, `New`, and `Mixed` correctly.
- Cancel during backup stops after the current file and logs cancellation.

Expected benefit:

- Safer changes as the app grows.
- More confidence before packaging releases.

## Suggested Next Implementation Order

1. Atomic temp-file copy with verification before final rename.
2. GUI progress stages for metadata batch analysis.
3. Configurable ExifTool batch timeout and retry behavior.
4. `.gitignore` and cleanup script.
5. Installer verification and license packaging.
6. Optional hash-based duplicate detection.

## Notes

The most important next step is atomic copy. DSB is a backup tool, so the core promise should be: source files are never changed, existing backups are protected, and newly copied files are only treated as complete after verification.
