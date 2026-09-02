# NDEX Patch Notes

## 2026-09-02 — Phase 3 job results (unreleased)

Not a version bump. `NDEX_VERSION` stays `0.9.1`.

Phase 2 recorded every finished job to a manifest, but nothing read those files back. Phase 3 is the read side.

- **Job Results** opens a read-only window listing recent jobs, newest first, with what each one copied, skipped, left ambiguous, or failed on. Problem files are listed first, with the reason recorded for each.
- Reachable from the Launcher footer (all apps), NDEX One's button row, Image Manager's **File** menu, Auto Selector's button row, and the NDEX Frame toolbar.
- Each Launcher workflow card shows its app's most recent job outcome under the folder status.
- The window can copy the problem paths to the clipboard and open the source, destination, or manifest folder. It never edits a manifest or a photograph.
- Frame gets a Qt version of the same view; the four Tk apps share one window.

### Phase 2 follow-up fixes

Six defects found reviewing the merged phase 2 code:

- Opening files or a folder in Frame now clears the previous select-handoff. Leaving it set made the Launcher's **Continue** re-import a stale pick list instead of the folder the user just opened.
- **Continue** now checks that a recorded handoff still parses and that its files still exist, instead of only that the file is present. When it does not, Frame reopens the last source folder.
- The Launcher no longer reports "Last folder missing" for a Frame session that has a stale folder but a working handoff.
- NDEX One's **Open Empty** now opens empty. It previously refilled the folders from the last saved session.
- Image Manager's **Send Picks to Frame…** reports an error when the handoff cannot be written, instead of opening Frame with nothing sent.
- Two jobs of the same type finishing in the same second get separate manifest files instead of one overwriting the other.

## 2026-09-02 — Phase 2 sessions and manifests (unreleased)

Not a version bump. `NDEX_VERSION` stays `0.9.1`. This is workflow state, not a GitHub release.

- Each app writes an explicit session document under `%LOCALAPPDATA%\NDEX\sessions\{app}.json`. The latest snapshot is also stored in `settings.json` under `shared.sessions` (add-only; `schema_version` remains 1). Legacy last-folder keys still hydrate Continue.
- Launcher Continue restores last work context: folders when they exist, and Frame `--handoff` when the select-handoff file exists. Missing folders fall back to Open Empty (`--open` only).
- Job manifests live under `%LOCALAPPDATA%\NDEX\manifests\` (backup, extract, export, select_handoff). They record copied / skipped / ambiguous / failed items and do not modify photographs.
- Image Manager **Send Picks to Frame…** writes a select-handoff JSON of picked JPG/PNG/TIFF files. Frame `--handoff` imports that list; `--output` preloads the export folder.
- NDEX One `--open` preloads GUI folders without entering CLI mode.

## 2026-09-01 — 0.9.1 public beta

NDEX is a public beta, not a 1.0 product. `NDEX_VERSION` is `0.9.1` (`NDEX_CHANNEL = "beta"`). Packages: `NDEX_v0.9.1.zip` / `NDEX_Setup_0.9.1.exe`.

GitHub tags `v1.0.0` and `v1.0.1` stay as historical downloads of this same line under a premature stable number.

If `NDEX_Setup_1.0.1.exe` is already installed, uninstall it before installing `0.9.1`. Inno Setup will treat `0.9.1` as older than `1.0.1`.

### Workflow correctness

- Backup copies write to a temp file, then replace the destination so a failed copy does not leave a truncated file.
- Image Manager XMP export: RAW sidecars use `stem.xmp`; JPG sidecars use `file.JPG.xmp`, so a RAW and JPG with the same stem no longer share one sidecar. Existing `stem.xmp` files are still read.
- Image Manager folder scans run on a background queue, so the UI stays responsive on large folders.
- Auto Selector reports ambiguous RAW filename matches instead of picking one silently.
- XMP export records per-file parse errors instead of aborting the whole batch.

### Foundation

- Shared `settings.json` updates take a lock, reload, merge, and write atomically (`schema_version`).
- Packaged apps write crash logs to `%LOCALAPPDATA%\NDEX\logs\`.
- Windows CI runs unit tests on Python 3.10 and 3.12 against `requirements.lock`.
- Release folders include `SHA256SUMS.txt`. The build fails if a git tag does not match `NDEX_VERSION`.
- Frozen launcher lookup stays in the exe directory and `Apps\`.

### UI consistency (published on GitHub as 1.0.1)

- Shared visual theme across Launcher, NDEX One, Image Manager, Auto Selector, and Frame.
- Consistent headers, cards, accent actions, and spacing in the Tk apps.
- NDEX Frame matches the suite chrome (Fusion stylesheet, side panels, primary Export All).
- Frame background color swatches no longer clip; Custom… stays fully visible.
- Those GitHub artifacts were `NDEX_v1.0.1.zip` / `NDEX_Setup_1.0.1.exe`.

### First public zip (published on GitHub as 1.0.0) and source-only main

- Windows users downloaded `NDEX_v1.0.0.zip` from GitHub Releases and ran `NDEX_Launcher.exe`.
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

### Packaged layout

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

- GitHub first shipped the suite installer as `NDEX_Setup_1.0.0.exe`. Current builds produce `NDEX_Setup_0.9.1.exe` into `C:\Program Files\NDEX`.
- Desktop icon and post-install run launch **NDEX Launcher**.
- MIT `LICENSE` plus English/Korean user agreement (`TERMS.md`, `TERMS.ko.md`). The installer shows the agreement before install. Copies go in `Docs\`. NDEX stays free of charge.
