# NDEX One

NDEX One is a desktop backup organizer for camera folders and SD cards. It scans enabled RAW and JPEG file types, reads the capture date when possible, and copies files into a structured backup layout:

```text
BackupRoot/YYYY/MM/MMDD/cr3
BackupRoot/YYYY/MM/MMDD/jpg
```

## Features

- Analyze before copying
- Brand-based RAW options: Canon CR3/CR2, Sony ARW/SRF/SR2, Nikon NEF/NRW
- Folder tree preview
- Duplicate handling: rename, skip, overwrite
- Copy verification: size, SHA-256, or none
- Dry run mode
- Log file output under `logs/`
- GUI mode and CLI mode

## Run

```powershell
python main.py
```

The app stores user settings and logs here:

```text
%LOCALAPPDATA%\NDEX\
```

On first run, NDEX One can reuse existing settings from `%LOCALAPPDATA%\DSB\`.

## CLI Examples

Analyze only:

```powershell
python main.py --source E:\DCIM --destination D:\PhotoBackup --analyze
```

Analyze and back up:

```powershell
python main.py --source E:\DCIM --destination D:\PhotoBackup --backup
```

Dry run with duplicate rename:

```powershell
python main.py --source E:\DCIM --destination D:\PhotoBackup --backup --dry-run --duplicate-policy rename
```

Back up with SHA-256 verification:

```powershell
python main.py --source E:\DCIM --destination D:\PhotoBackup --backup --verify-mode sha256
```

Include specific file types from CLI:

```powershell
python main.py --source E:\DCIM --destination D:\PhotoBackup --backup --type cr3 --type cr2 --type arw
```

## Metadata Strategy

1. `ExifTool` if available
2. Pillow EXIF for JPG/JPEG if installed
3. File modified time as fallback

`ExifTool` is strongly recommended for reliable `.CR3` metadata extraction.

The scanner reads metadata in batches when ExifTool is available, which avoids starting a separate ExifTool process for every file.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Build EXE

Put `exiftool.exe` here first:

```text
vendor/exiftool/exiftool.exe
vendor/exiftool/exiftool_files/...
```

Build the portable GUI package:

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build.ps1
```

Build a single executable:

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build.ps1 -OneFile
```

Build the installer too:

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build.ps1 -Installer
```

Notes:

- `PyInstaller` is installed by the build script if needed.
- `-OneFile` builds `dist\NDEX_One_OneFile.exe`.
- `Inno Setup` is required only for the installer step.
- The packaged app uses `ExifTool` internally. The end user only runs `NDEX_One.exe`.
