# NDEX Patch Notes

## 2026-09-01

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
