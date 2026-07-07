# NDEX Image Manager

NDEX Image Manager is the second program in the NDEX series. It is kept in its own
folder so it does not mix with the existing NDEX One backup app.

## Goals

- Browse JPG and RAW shooting folders.
- Detect RAW/JPG pairs by matching the base filename.
- Show previews, thumbnails, basic EXIF, pick status, rating, and backup status.
- Store catalog, selection state, and cache paths in `.dsb_cache/catalog.sqlite`.
- Back up selected images into the NDEX date folder structure:
  `YYYY/MM/MMDD/EXT`.
- Keep scanner, catalog, cache, metadata, backup, and UI as separate modules so
  future NDEX series integration can reuse the services without depending on the
  current Tkinter UI.

## Run

From this repository root:

```powershell
python -m dsb_image_manager.main
```

CLI scan:

```powershell
python -m dsb_image_manager.main --source "D:\Photos\Shoot" --scan
```

Back up files marked `Pick`:

```powershell
python -m dsb_image_manager.main --source "D:\Photos\Shoot" --backup-picked --backup-destination "E:\Photo Backup"
```

## Structure

- `dsb_image_manager/core`: shared models and file type definitions.
- `dsb_image_manager/services`: scan, EXIF, cache, catalog, and backup logic.
- `dsb_image_manager/ui`: GUI layer. This can be replaced with PySide6 later.
- `tests`: focused regression tests for scan, pair, selection, and backup logic.

## Current RAW Preview Behavior

JPG files are displayed directly and receive generated thumbnails. RAW files first
try to extract an embedded JPEG preview through ExifTool. If no preview is
available, the app creates a clear placeholder thumbnail and marks proxy status as
`failed`. This keeps the v0.1 browser usable while leaving room for rawpy/LibRaw
rendering in a later version.
