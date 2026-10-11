# NDEX 0.9.6 Beta — build and release validation

Validation date: 2026-10-11. Release target: [v0.9.6](https://github.com/electroaria7/NDEX/releases/tag/v0.9.6). Source changes: [PR #23](https://github.com/electroaria7/NDEX/pull/23).

## Build provenance

- Application source: `8185b64beb7402d06f7e926c93414a4374cbf78a`. Later commits only change release documentation; the package was reassembled (`build_all.ps1 -SkipBuild -Installer`) so its Docs folder matches them.
- Windows x64, Python 3.12.10 (project `.venv`). Runtime dependencies match `requirements.lock` (Pillow 12.3.0, PySide6 6.11.2). Build tooling: PyInstaller 6.11.1, Inno Setup 6.7.3.
- `build_all.ps1 -Installer` rebuilt all five EXEs into `release/NDEX_v0.9.6` and compiled the installer. Each EXE's bundled `ndex_common.version` reads `NDEX_VERSION = "0.9.6"`, `NDEX_CHANNEL = "beta"`.
- Each EXE bundles `ndex_common/locales/en.json` and `ko.json` and the new `ndex_common.i18n` and `ndex_common.raw_formats` modules (checked in the PyInstaller archives).

## Source and CI checks

| Suite | Passed |
| --- | ---: |
| Common / One / integration | 287 (1 skipped) |
| Image Manager | 112 |
| Auto Selector | 73 |
| Launcher | 27 |
| Frame | 230 |
| **Total** | **729** |

Suites used temporary `LOCALAPPDATA`; Qt used `QT_QPA_PLATFORM=offscreen`. The Image Manager suite was run three more times in a row after the thumbnail-worker shutdown fix (all passed; before the fix it failed about one run in three and could leave a process running). `tools/i18n_extract.py --check`: 793 messages and 35 plural entries, 0 missing, 0 unused. CI_LINE

RAW formats were checked with 19 real CC0 samples (Canon CR3/CR2/CRW, Sony ARW/SR2/SRF, Nikon NEF/NRW); see [RAW compatibility](RAW_Compatibility.md). Embedded previews were also extracted from CR2 and ARW files in a Korean-named folder (5184×3456 and 7008×4672).

## Packaged execution

`tests/smoke_release.py` ran against the package with disposable photos, Korean paths and isolated application data: One backup with SHA-256 verification, Image Manager catalog scan, Auto Selector RAW copy with XMP, a repeated Auto Selector run that preserved existing RAWs and user-edited XMP, and Frame export. All five invocations exited with code 0 and the checksum comparison passed.

Each of the five EXEs was started hidden with an empty isolated workspace and stayed running for 35 seconds with empty stderr and no crash logs; the process trees were then terminated. The packaged Launcher was also started with language `ko` and a user override catalog in `%LOCALAPPDATA%\NDEX\locales`; the translated labels appeared, confirming frozen-path loading. This checks startup and wiring, not full packaged GUI interaction.

## Distribution integrity

The release folder contains 14 files (five EXEs, eight documentation/legal files, `SHA256SUMS.txt`); every payload hash matches the internal manifest. Packaged `PATCH_NOTES.md`, `README.md` and `README.ko.md` match their source files byte for byte. ZIP CRC and per-file SHA-256 checks passed; the ZIP keeps the `NDEX_v0.9.6/` layout. `SHA256SUMS-0.9.6.txt` covers the installer and ZIP.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `NDEX_Setup_0.9.6.exe` | 629027442 | `d87daaf99b17c3f15ca18b5464b6012e1441f4bae0d290304d10e0caa8f9a17c` |
| `NDEX_v0.9.6.zip` | 625164566 | `5e902ec85fc0d1de53e135398885389a23d441208cef9c94c1f41569cf8d3978` |
| `SHA256SUMS-0.9.6.txt` | 171 | `d42a0275c541ffe896d0135e0f8d48c415ee3794e6980d08d653778b567cedb6` |

Publication uses a GitHub **prerelease** at `v0.9.6`; uploaded asset sizes and digests are compared with this table before publishing. Older releases are retained.

## Limits

- Korean translation values are still empty; the UI stays English until translations are added (see [Localization](Localization.md)).
- Lightroom/Evoto XMP interpretation, real portrait RAW orientation and large SD-card performance remain unverified.
- Fresh install, uninstall and upgrade from older installs were not repeated for this release.
- Packaged GUI interaction and high-DPI multi-monitor checks were not completed.
- The EXEs are unsigned and the release remains a beta.
