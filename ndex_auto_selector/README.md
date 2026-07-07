# NDEX Auto Selector

NDEX Auto Selector is the third NDEX utility. It reads a folder of selected JPG
files, finds CR3 originals with the same base filename, and copies those CR3
files into a working folder.

## Workflow

1. Choose the folder that contains the original CR3 files.
2. Choose the folder that contains selected JPG files.
3. Choose a working folder.
4. Analyze matches, then copy the matched CR3 originals.

Matching is case-insensitive and uses the filename stem:

```text
IMG_1024.JPG -> IMG_1024.CR3
```

If the selected JPG has extra text before or after the camera filename, the app
also extracts `IMG_0000` style four-digit IDs and matches by that token:

```text
album_pick_IMG_1024_edit.JPG -> IMG_1024.CR3
```

## Run

From the repository root:

```powershell
python -m ndex_auto_selector.main
```

Analyze from CLI:

```powershell
python -m ndex_auto_selector.main --raw-source "E:\DCIM" --selected-jpg "D:\Selects" --analyze
```

Copy matched CR3 files:

```powershell
python -m ndex_auto_selector.main --raw-source "E:\DCIM" --selected-jpg "D:\Selects" --work-folder "D:\Work" --copy
```

Copy matched CR3 files and create XMP sidecars that mark them as selected:

```powershell
python -m ndex_auto_selector.main --raw-source "E:\DCIM" --selected-jpg "D:\Selects" --work-folder "D:\Work" --copy --write-xmp --xmp-rating 5
```

The sidecar is created next to the copied CR3:

```text
IMG_1024.CR3
IMG_1024.xmp
```

The XMP stores `xmp:Rating="5"`, `xmp:Label="NDEX Selected"`, and a
`NDEX Selected` keyword so Lightroom-compatible apps can identify the selected
originals without modifying the RAW file itself.

## Build One-File EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\ndex_auto_selector\build_package.ps1
```

The output is:

```text
ndex_auto_selector/dist/NDEX_Auto_Selector.exe
```
