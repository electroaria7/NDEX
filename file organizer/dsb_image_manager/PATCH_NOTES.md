# DSB Image Manager Patch Notes

## 2026-05-08

### Initial Image Manager App

- Created a separate `dsb_image_manager` project folder so the second DSB program stays isolated from the existing backup app.
- Added a modular package structure:
  - `core`: file types and shared data models.
  - `services`: scanner, catalog, cache, metadata, backup, and export logic.
  - `ui`: Tkinter GUI layer.
- Added SQLite catalog storage at `.dsb_cache/catalog.sqlite`.
- Added JPG/RAW scanning with recursive folder support.
- Added RAW/JPG pair detection by matching base filenames.
- Added JPG thumbnail generation.
- Added RAW embedded preview extraction through bundled ExifTool, with fallback placeholder thumbnails.
- Added basic EXIF extraction for capture date, camera, lens, exposure, ISO, dimensions, color space, GPS, and file size.

### Rating, Pick, And Fullscreen Workflow

- Added Pick / Maybe / Reject / Unrated status support.
- Added 0-5 rating support.
- Added clickable star rating controls in the GUI.
- Added keyboard shortcuts:
  - `P`: Pick
  - `M`: Maybe
  - `X`: Reject
  - `U`: Unrated
  - `0-5`: rating
  - Arrow keys: previous / next image
  - `F`: fullscreen preview
- Added fullscreen image viewer.
- Added fullscreen previous / next navigation.
- Added fullscreen rating and pick controls.
- Added compact fullscreen EXIF overlay with filename, rating, pick status, camera, lens, aperture, shutter speed, ISO, and resolution.

### Layout And View Options

- Added EXIF detail modes:
  - `Simple`
  - `Full`
- Added image layout presets:
  - `50%`
  - `80%`
  - `Full`
- Added preview background choices:
  - `50% Gray`
  - `Dark Gray`
  - `Light Gray`
- Applied preview background choices to both the main preview and fullscreen viewer.

### Export And Backup

- Added `Backup Picked` workflow using the DSB date folder structure.
- Added multi-select support in the catalog list.
- Added `Export Selected` workflow.
- Export keeps original files unchanged and copies selected files to a chosen folder.
- Added export rename pattern tokens:
  - `{date}`
  - `{time}`
  - `{index}`
  - `{index2}`
  - `{index3}`
  - `{index4}`
  - `{name}`
  - `{rating}`
  - `{pick}`
  - `{ext}`
- Added duplicate handling options for export:
  - `rename`
  - `skip`
  - `overwrite`

### UI Cleanup

- Moved primary actions into a top menu bar:
  - `File`
  - `Selection`
  - `Filter`
  - `View`
  - `Help`
- Removed crowded action buttons from the toolbar.
- Kept the toolbar focused on quick filters and short guidance.
- Replaced sort dropdowns with clickable catalog column headers.
- Added ascending / descending sort indicators to column headers.
- Simplified the catalog columns to:
  - `File`
  - `Type`
  - `Pick`
  - `Rating`
  - `Capture Date`
- Added a top information area showing current folder and visible image/filter status.
- Added a compact EXIF summary line in the right panel.
- Moved long shortcut help into `Help > Shortcuts`.
- Flattened visual styling to reduce boxed text and heavy borders.
- Updated preview and EXIF areas to cleaner card/panel styling.

### Packaging

- Added `build_package.ps1`.
- Added PyInstaller one-file packaging.
- Bundled ExifTool with the exe package.
- Switched the exe to `--windowed` mode so the app opens without a background command window.
- Current exe output:
  - `dsb_image_manager/dist/DSB_Image_Manager.exe`

### Tests And Verification

- Added service tests for:
  - JPG/RAW pair detection.
  - SQLite selection persistence.
  - DSB backup date folder output.
  - Export rename pattern output.
  - Export pattern path sanitization.
- Verified:
  - `python -m compileall dsb_image_manager`
  - `python -m unittest discover -s dsb_image_manager\tests`
  - GUI construction smoke test.
  - PyInstaller windowed exe build.
  - Exe smoke test with CLI scan arguments.

### Security And Safety Review

- Confirmed no `shell=True`, `eval`, `exec`, or `os.system` usage.
- ExifTool is called through list-based `subprocess.run`, not shell string execution.
- Original image files are not renamed or moved.
- Export and backup use copy-based workflows.
- Export filename patterns sanitize path separators and invalid filename characters.
- Added regression coverage so export patterns cannot create nested paths through `/`, `\`, or `..`.
- Overwrite behavior is available only when explicitly selected.


## 2026-07-03

### XMP Sidecar Export (NDEX interop)

- Added shared `ndex_common.xmp` module at the repo root; Auto Selector's XMP writer was extracted into it and both apps now use the same code.
- Added `XmpExportService`: writes `.xmp` sidecars next to original files for picked/rated images. Originals are never modified.
- Mapping: rating -> `xmp:Rating`, Pick -> `xmp:Label="NDEX Selected"` + keyword `NDEX Pick`, Maybe/Reject -> keywords `NDEX Maybe`/`NDEX Reject`.
- Existing sidecars are merged, not overwritten (unknown fields and keywords preserved).
- GUI: `File > Export XMP Sidecars (Picked/Rated)`.
- CLI: `--export-xmp` flag.
- Tests: 3 new tests (write, skip unrated, merge into existing sidecar).
