# NDEX Frame Patch Notes

## 2026-09-01

### Main-window framing shortcuts

- Added ratio shortcut buttons on the right Frame panel: `3:4`, `4:5`, `1:1`.
- Ratio still has editable width/height spins for values that are not in that list.
- Ratio changes apply to the whole loaded session immediately (shared working frame).
- Replaced the main-window hex color field with background swatches:
  - White `#FFFFFF`
  - Bright Gray `#D0D0D0`
  - Medium Gray `#808080`
  - Black `#000000`
- Added **Custom…** to open the system color picker for any other background.
- Added photo-size shortcut buttons: `80%`, `90%`, `95%` (slider 10–100% remains).
- Photo size and X/Y stay per-photo until **Apply Current Framing to All** copies the selected photo’s size and position onto every loaded image (ratio and background were already session-wide).
- Frame Preset and Output Profile stay independent. **Manage Presets** / **Save as Frame Preset** are unchanged; the main panel is the place to try a look before saving.

### Export progress

- Added a bottom-bar progress control (`Export progress`) that appears while a batch runs.
- The bar shows `filename · current / total` and matches the status-bar count.
- The bar resets and hides when export finishes or is cancelled.
- **Cancel** still appears only while an export thread is running.

### Tests

- Covered swatch accessible names, ratio/size shortcut buttons, Apply All, and progress-bar show/update/hide.

### Suite installer and launcher workflow

- NDEX Launcher already exposes the four-step workflow: Backup (NDEX One) → Select (Image Manager) → Extract (Auto Selector) → Frame (NDEX Frame).
- Replaced the NDEX One-only Inno Setup script with a **NDEX 1.0.0 suite installer**.
- Installs the assembled portable folder into `{autopf}\NDEX` so all five EXEs stay side by side (required for in-app handoff).
- Start Menu group **NDEX** lists Launcher plus numbered workflow shortcuts 1–4, including **4. Frame & Export - NDEX Frame**.
- Desktop icon launches **NDEX Launcher**.
- Build with `build_all.ps1 -Installer` (requires Inno Setup `ISCC`) to produce `release\NDEX_Setup_1.0.0.exe`.


## 2026-08-30

### Initial NDEX Frame app

- Added standalone `ndex_frame` with crop-free FIT geometry and a preview-first PySide6 window.
- Preview and export share one `RenderPlan` so the on-screen frame matches the file that is written.
- Built-in defaults: Frame Preset White 3:4, Output Profile Instagram Feed HQ (1080×1440 JPEG, Quality 95, 4:4:4, sRGB ICC).
- Color-managed Master → sRGB conversion; JPEG/PNG/WebP export with atomic temp-then-rename.
- Masters and existing outputs are never overwritten (skip or auto-rename only).
- Folder/file import, thumbnails, per-image scale/position overrides, Reset Override.
- Batch **Export Selected** / **Export All** with preflight, completion summary, and cancel.
- Packaged as `NDEX_Frame.exe`; Launcher step **4. Frame & Export**; `build_all.ps1` builds Frame before Launcher.
- Settings in `%LOCALAPPDATA%\NDEX\config\settings.json` (`frame` section); Frame data under `%LOCALAPPDATA%\NDEX\Frame\`.
