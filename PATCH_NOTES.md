# NDEX Patch Notes

## 2026-09-01

### Release 1.0.0 and source-only main

- Windows users download `NDEX_v1.0.0.zip` from GitHub Releases and run `NDEX_Launcher.exe`.
- The `main` branch is source only. The extra `distribution` branch was removed.
- `main` is protected: pull requests required, force-push and deletion blocked.
- Rebuilt 1.0.0 with Pillow `>=12.3.0` so the packaged apps pick up current image-decoder fixes.
- English and Korean README/terms now point at Releases instead of cloning source for install.
- Generated per-app PyInstaller `build/` output is no longer tracked on `main`.
- EXEs remain unsigned. An Inno Setup installer is produced only when `ISCC` is installed.

### Quick start and bilingual docs

- Root `README.md` is English. `README.ko.md` has the same sections in Korean.
- Both files open with a **Quick start** for installer, portable folder, and source.
- Packaged copies live in `Docs\` next to the apps.

### Structured 1.0 package

Installer and portable folder now share this layout:

```
NDEX_Launcher.exe
Apps\NDEX_One.exe
Apps\NDEX_Image_Manager.exe
Apps\NDEX_Auto_Selector.exe
Apps\NDEX_Frame.exe
Docs\...
```

- NDEX One is shipped as `Apps\NDEX_One.exe` (built from the one-file EXE).
- Launcher still finds workflow apps in `Apps\` (and still accepts the old `NDEX_One_OneFile.exe` name if present).
- Start Menu shortcuts point at the `Apps\` executables.
- Build with `build_all.ps1` or `build_all.ps1 -Installer`.

### NDEX Frame

See `ndex_frame/PATCH_NOTES.md` (copied to `Docs\FRAME_PATCH_NOTES.md`): ratio/color/size shortcuts, Apply All, export progress bar.

### Installer

- Suite installer `NDEX_Setup_1.0.0.exe` installs the structured folder into `C:\Program Files\NDEX`.
- Desktop icon and post-install run launch **NDEX Launcher**.
- MIT `LICENSE` plus English/Korean user agreement (`TERMS.md`, `TERMS.ko.md`). The installer shows the agreement before install. Copies go in `Docs\`. NDEX stays free of charge.
