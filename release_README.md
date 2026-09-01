# NDEX — Photo Workflow Suite

Portable release. No installation needed: keep the five EXE files in one
folder so the apps can launch each other (workflow handoff).

The Windows installer (`NDEX_Setup_1.0.0.exe`) puts that same folder under
`C:\Program Files\NDEX` and adds Start Menu shortcuts for the four-step
workflow. Open **NDEX Launcher** first; it covers Backup, Select, Extract,
and Frame.

## Apps

| App | Role |
| --- | --- |
| `NDEX_Launcher.exe` | Workflow hub — shows backup / select / extract / frame steps and recent sessions, launches each app |
| `NDEX_One_OneFile.exe` | Backup camera/SD files into a date-based library (atomic copy, verification, smart duplicate skip) |
| `NDEX_Image_Manager.exe` | Browse JPG/RAW pairs, pick and rate, backup picks, export XMP sidecars |
| `NDEX_Auto_Selector.exe` | Match selected JPGs to CR3 originals, copy to a work folder, write XMP (can carry JPG star ratings) |
| `NDEX_Frame.exe` | Preview Masters and batch-export crop-free, color-managed Instagram images |

## Typical workflow

1. `NDEX_Launcher.exe` → **1. Backup** — copy the SD card into your library.
2. **2. Select & Rate** — pick/rate images, then `File > Export XMP Sidecars`.
3. **3. Extract** — match selected JPGs to CR3 and hand the work folder to Lightroom/Evoto.
4. **4. Frame & Export** — open NDEX Frame on the finished Masters, preview the White 3:4 frame, and export Instagram Feed HQ JPEGs.

Each app also works standalone — open only what you need.

## NDEX Frame

Open JPG/JPEG, PNG, or TIFF Masters. Preview and export use the same crop-free FIT layout. Frame Preset and Output Profile are independent (defaults: White 3:4 and Instagram Feed HQ 1080×1440 JPEG, Quality 95, 4:4:4, sRGB ICC). Masters and existing outputs are never overwritten (skip or auto-rename).

On the right Frame panel:

- **Ratio** shortcuts `3:4` / `4:5` / `1:1` apply to every loaded photo.
- **Background** swatches White, Bright Gray, Medium Gray, Black, plus **Custom…**, also apply to the whole session.
- **Photo Size** slider and `80%` / `90%` / `95%` apply to the selected photo until you click **Apply Current Framing to All**.
- During **Export Selected** / **Export All**, a progress bar shows `filename · current / total`. Use **Cancel** to stop.

Saved presets stay in **Manage Presets**. Frame data lives under `%LOCALAPPDATA%\NDEX\Frame\`.

## Patch notes (2026-09-01)

- NDEX Frame: ratio and background shortcuts on the main screen (no hex typing).
- NDEX Frame: photo-size presets 80 / 90 / 95% and **Apply Current Framing to All**.
- NDEX Frame: export progress bar with filename and current / total.
- NDEX installer: ships all five apps into `C:\Program Files\NDEX`, with Start Menu shortcuts for the 1–4 workflow and a desktop icon for NDEX Launcher.

## Settings

All apps share one settings file:
`%LOCALAPPDATA%\NDEX\config\settings.json`

## Notes

- One-file EXEs unpack at launch, so first start can take a few seconds.
- ExifTool (bundled where needed) is a third-party tool; its license notes
  are in `third_party_licenses/` when present.
- Qt/PySide6, shiboken6, and Pillow notices are in `THIRD_PARTY_NOTICES.md`.
