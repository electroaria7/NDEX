# NDEX — Photo Workflow Suite

Portable release. No installation needed: keep the four EXE files in one
folder so the apps can launch each other (workflow handoff).

## Apps

| App | Role |
| --- | --- |
| `NDEX_Launcher.exe` | Workflow hub — shows backup / select / extract steps and recent sessions, launches each app |
| `NDEX_One_OneFile.exe` | Backup camera/SD files into a date-based library (atomic copy, verification, smart duplicate skip) |
| `NDEX_Image_Manager.exe` | Browse JPG/RAW pairs, pick and rate, backup picks, export XMP sidecars |
| `NDEX_Auto_Selector.exe` | Match selected JPGs to CR3 originals, copy to a work folder, write XMP (can carry JPG star ratings) |

## Typical workflow

1. `NDEX_Launcher.exe` → **1. Backup** — copy the SD card into your library.
2. **2. Select & Rate** — pick/rate images, then `File > Export XMP Sidecars`.
3. **3. Extract** — match selected JPGs to CR3 and hand the work folder to Lightroom/Evoto.

Each app also works standalone — open only what you need.

## Settings

All apps share one settings file:
`%LOCALAPPDATA%\NDEX\config\settings.json`

## Notes

- One-file EXEs unpack at launch, so first start can take a few seconds.
- ExifTool (bundled where needed) is a third-party tool; its license notes
  are in `third_party_licenses/` when present.
