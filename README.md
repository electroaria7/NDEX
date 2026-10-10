# NDEX — Photo Workflow Suite

[한국어](README.ko.md)

**Public beta · 0.9.4**

Windows desktop tools for a photo workflow: backup → select → extract masters → frame & export.
Each app can run alone. Together they share XMP sidecars and one settings file. Actual XMP interpretation in Lightroom / Evoto still needs separate validation.

This is a **public beta**, not a 1.0 product. EXEs are unsigned, so Windows SmartScreen may warn. Expect more changes before a stable release.

## Public beta

- Current version: **0.9.4 Beta**. Packages: `NDEX_v0.9.4.zip` (portable) and `NDEX_Setup_0.9.4.exe` (installer). See the [0.9.4 Beta release](https://github.com/electroaria7/NDEX/releases/tag/v0.9.4) for downloads.
- GitHub tags `v1.0.0` and `v1.0.1` were this same beta line with a premature stable number. Historical downloads, including `v0.9.3`, remain separate from the 0.9.4 release.
- If `NDEX_Setup_1.0.1.exe` is already installed, uninstall it before installing `0.9.4`. Windows treats `0.9.4` as older than `1.0.1`.
- Changelog: [PATCH_NOTES.md](PATCH_NOTES.md).

## Quick start

**What's new in 0.9.4**

- Image Manager runs backup, file export, and XMP export in the background with progress and cancellation. Scans and file jobs run one at a time.
- Auto Selector adds cancellation, rejects stale analysis, and reuses identical numbered RAW copies when a job is repeated. Image Manager sends only picked JPGs to it, and exact RAW filenames take priority over camera-ID matches.
- One, Auto Selector, and Frame retain unprocessed cancelled files for Retry Failed; Image Manager records them in Job Results. All four working apps wait for active jobs and their results before closing.
- Frame reuses decoded previews; folder scans avoid entering excluded backup/work/cache directories. Bulk Image Manager selection updates use one database transaction.
- Audit fixes cover Korean RAW paths and capture dates, RAW/JPG pairing, stale thumbnails, XMP pick updates, settings recovery, and Frame color/profile handling.

Cancellation takes effect after the current file's copy, verification, or render, or the current metadata batch. One waits for analysis to finish when closing during analysis.
The verified atomic-copy behavior from 0.9.3 remains, including preservation of existing RAW and XMP files under Auto Selector's duplicate `skip` policy.

Large real-world RAW/SD-card benchmarks and Lightroom/Evoto compatibility remain follow-up work.
Review details: [October 9 audit](docs/Improvement_Review_2026-10-09.md), [October 10 UI and task safety](docs/Improvement_Review_2026-10-10.md).

Preflight capacity summaries, CSV/HTML reports, localization, and release automation follow this work.
See the [consolidated roadmap](https://github.com/electroaria7/NDEX/blob/main/docs/obsidian/NDEX/Roadmap.md).

**Windows package (recommended)**

1. Download `NDEX_v0.9.4.zip` from the [0.9.4 Beta release](https://github.com/electroaria7/NDEX/releases/tag/v0.9.4) when available.
2. Unzip the folder. Keep `Apps\` together.
3. Double-click `NDEX_Launcher.exe`.
4. Use the four cards: **1. Backup** → **2. Select & Rate** → **3. Extract** → **4. Frame & Export**.

**Installed (`NDEX_Setup_0.9.4.exe`)**

1. Run the installer. Files go to `C:\Program Files\NDEX`.
2. Open **NDEX Launcher** from the Start menu or the desktop icon.
3. Follow the same four cards.

This GitHub `main` branch is **source code**, not the install package.

**From source (developers)**

```powershell
pip install -r requirements.txt
python -m ndex_launcher.main
```

First launch of a one-file EXE can take a few seconds while it unpacks.

## Apps

| App | Role |
| --- | --- |
| **NDEX Launcher** | Workflow hub — four-step dashboard, Continue last session, launch each app |
| **NDEX One** | Camera/SD → date-folder library. Atomic copy, size/SHA-256 verify, hash duplicate skip |
| **NDEX Image Manager** | JPG/RAW pair browse, Pick/stars, select backup, XMP export |
| **NDEX Auto Selector** | Match select JPGs to RAW masters + XMP (can carry JPG star ratings) |
| **NDEX Frame** | Place finished Masters on a crop-free canvas and export color-managed Instagram JPEG/PNG/WebP |

Supported RAW: CR3 · CR2 · ARW · SRF · SR2 · NEF · NRW  
Filename matching: Canon `IMG_0001` · Nikon `DSC_0001`/`_DSC0001` · Sony `DSC00001`. Exact names take priority; a camera ID inside a renamed JPG can match a RAW whose name begins with that ID. Prefixed RAW names require an exact filename match.

NDEX Frame input: JPG/JPEG · PNG · TIFF. Masters and existing outputs are never overwritten.

## Workflow

```
Camera/SD ─▶ NDEX One ─▶ date library
                              │  "Open in Image Manager"
                              ▼
                    NDEX Image Manager ─▶ Pick/stars ─▶ XMP export
                              │  "Send to Auto Selector"
                              ▼
                     NDEX Auto Selector ─▶ work folder (RAW + XMP)
                              ▼
                       Lightroom / Evoto
                              ▼
                          NDEX Frame ─▶ Instagram deliverables
```

## NDEX Frame

Preview and export use the same crop-free FIT layout. Frame Preset and Output Profile are independent.

Defaults: Frame Preset **White 3:4**, Output Profile **Instagram Feed HQ** (1080×1440 JPEG, Quality 95, 4:4:4, sRGB ICC).

| Control | What it does |
| --- | --- |
| **Ratio** | `3:4` · `4:5` · `1:1`, or type numbers. Applies to **all loaded photos** |
| **Background** | White · Bright Gray · Medium Gray · Black swatches, or **Custom…**. All photos |
| **Photo Size** | Slider or `80%` · `90%` · `95%`. **Selected photo** only |
| **Apply Current Framing to All** | Copies current ratio, background, size, and position to every photo |

Set **Output Folder**, then **Export Selected** or **Export All**. A progress bar shows `filename · current / total`. **Cancel** stops the batch. Existing files are skipped or auto-renamed.

Frame data: `%LOCALAPPDATA%\NDEX\Frame\`  
Shared settings `frame` section: `%LOCALAPPDATA%\NDEX\config\settings.json`

## Packaged layout (installer and portable)

```
NDEX_v0.9.4\                  also installed as C:\Program Files\NDEX\
  NDEX_Launcher.exe           start here
  SHA256SUMS.txt
  Apps\
    NDEX_One.exe
    NDEX_Image_Manager.exe
    NDEX_Auto_Selector.exe
    NDEX_Frame.exe
  Docs\
    README.md                 this file (English)
    README.ko.md              same content in Korean
    PATCH_NOTES.md
    FRAME_PATCH_NOTES.md
    LICENSE
    TERMS.md
    TERMS.ko.md
    THIRD_PARTY_NOTICES.md
    Licenses\
```

Start Menu **NDEX** has numbered shortcuts 1–4 plus Launcher. Changelog: [PATCH_NOTES.md](PATCH_NOTES.md).

## Build

Windows, Python 3.10+, `pip install -r requirements.txt` (Pillow, PySide6), PyInstaller 6.11.1. Installer also needs Inno Setup (`ISCC`).

```powershell
powershell -ExecutionPolicy Bypass -File .\build_all.ps1
powershell -ExecutionPolicy Bypass -File .\build_all.ps1 -Installer
```

Output: `release\NDEX_v0.9.4\` (portable package) and `release\NDEX_Setup_0.9.4.exe`.

```powershell
python -m ndex_launcher.main
python main.py
python -m dsb_image_manager.main
python -m ndex_auto_selector.main
python -m ndex_frame
```

## Tests

```powershell
python -m unittest discover -s tests
python -m unittest discover -s dsb_image_manager\tests
python -m unittest discover -s ndex_auto_selector\tests
python -m unittest discover -s ndex_launcher\tests
python -m unittest discover -s ndex_frame\tests
powershell -ExecutionPolicy Bypass -File .\ndex_frame\tests\smoke_packaged.ps1
```

## Repository layout

```
ndex_common/          shared xmp · rating · launch · settings · branding · version
src/ + main.py        NDEX One
dsb_image_manager/    NDEX Image Manager
ndex_auto_selector/   NDEX Auto Selector
ndex_frame/           NDEX Frame
ndex_launcher/        NDEX Launcher
build/, *_package.ps1 PyInstaller / Inno Setup
vendor/exiftool/      ExifTool (CR3 metadata and previews)
```

## License and user agreement

NDEX is free open-source software under the [MIT License](LICENSE). Installing or running it means you accept the [User Agreement](TERMS.md) ([한국어](TERMS.ko.md)).

Your photographs stay on your computer. There is no warranty. Third-party components (Qt/PySide6, Pillow, ExifTool) keep their own licenses; see `THIRD_PARTY_NOTICES.md`.
