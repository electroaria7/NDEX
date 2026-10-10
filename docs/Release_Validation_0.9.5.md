# NDEX 0.9.5 Beta — build and release validation

Validation date: 2026-10-10. Release target: [v0.9.5](https://github.com/electroaria7/NDEX/releases/tag/v0.9.5). Source changes: [PR #21](https://github.com/electroaria7/NDEX/pull/21).

## Build provenance

- Application source: `b14897e338dd3d95e8f596dac1fa52995fd59f06`. Subsequent release-documentation changes do not modify application code.
- Windows x64, Python 3.12.10 in the existing isolated `.build_tools/release-0.9.4-venv` environment, with system site packages disabled. This environment name is historical; the rebuilt app version is 0.9.5.
- Runtime dependencies match `requirements.lock`: Pillow 12.3.0, PySide6 / Addons / Essentials / shiboken6 6.11.2. `pip check` passed. Build tooling: PyInstaller 6.11.1, hooks 2026.8, Inno Setup 6.7.3.
- `build_all.ps1 -Installer` completed successfully. All five EXEs were rebuilt into the new `release/NDEX_v0.9.5` package and the installer was compiled. The EXEs' bundled version assignments are `NDEX_VERSION = "0.9.5"` and `NDEX_CHANNEL = "beta"`; the installer's PE ProductVersion is `0.9.5`.
- Static comparison of bundled code with source passed for all five entry points and 185 repository modules: Launcher 25, One 31, Image Manager 37, Auto Selector 29, Frame 63. Nested code objects were compared after normalizing source filenames; no bundled repository code was executed for this comparison.

As in 0.9.4, PyInstaller warned about unused optional Qt SQL client DLLs, PySide deployment tooling (`project_lib`), and a `pkg_resources` hidden import. An unused QML hook also triggered a warning-formatting `TypeError`. Frame uses Qt Core/Gui/Widgets rather than QML; these diagnostics did not stop EXE generation. The packaged startup and export checks below passed. This does not validate the unused optional Qt integrations.

## Source and CI checks

| Suite | Passed |
| --- | ---: |
| Common / One / integration | 244 |
| Image Manager | 43 |
| Auto Selector | 71 |
| Launcher | 23 |
| Frame | 171 |
| **Total** | **552** |

All suites passed in the isolated build environment after the version change. Each suite used temporary `LOCALAPPDATA`; Qt used `QT_QPA_PLATFORM=offscreen`. [CI run 38085313160](https://github.com/electroaria7/NDEX/actions/runs/38085313160) passed on Windows with Python 3.10 and 3.12 at the application source commit above.

The [integration review](Improvement_Review_2026-10-10.md#추가-ui-개편-통합-검수--featuiux-polish) records the four additional fixes and minimum-window widget checks. Native capture returned a black screen; widget-size/event-loop checks are not visual acceptance or high-DPI testing.

## Packaged execution

`tests/smoke_release.py` ran against the new package using disposable photos, Korean paths, and isolated application data:

1. **One:** copied two JPEGs and two synthetic CR3 fixtures, verified their SHA-256 values and job records, and placed JPEGs by capture date.
2. **Image Manager:** scanned the backup into a four-record catalog.
3. **Auto Selector:** copied two matched RAW fixtures and created their XMP sidecars while preserving unrelated destination files.
4. **Repeated Auto Selector run:** copied 0, skipped 2, failed 0. Existing RAWs and user-edited XMP remained byte-identical; no extra numbered copies were created.
5. **Frame:** exported a Korean-named JPEG to 1080×1440, preserved ICC and copyright metadata, removed GPS, and left the source unchanged.

All five CLI invocations exited with code 0 and empty stderr. Separate hidden startup checks kept each of the five apps alive for at least 30 seconds with isolated empty workspaces; no crash logs or stderr were produced. Only the test process trees were terminated afterward. This checks startup, not packaged GUI interaction or graceful closing.

## Distribution integrity

The release folder contains 14 files: five EXEs, eight documentation/legal files, and `SHA256SUMS.txt`. Every one of the 13 payload hashes matches the internal checksum manifest, with no unlisted payload. Packaged English/Korean README and patch notes match their source files byte for byte. The installer compile log includes all 14 files.

ZIP CRC validation and SHA-256 verification of every payload file passed. The ZIP preserves the `NDEX_v0.9.5/` folder layout. A separate `SHA256SUMS-0.9.5.txt` covers the installer and ZIP.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `NDEX_Setup_0.9.5.exe` | 522163185 | `ad1368d0b3a0166a0d2fdc3633a8c2677c858f6a03f60a457f52b042a8c5187d` |
| `NDEX_v0.9.5.zip` | 518558936 | `46e2e8b03d7585563206341a7e41ee39e4ef0ed66e3a4c1e6a995a6ac795ddce` |
| `SHA256SUMS-0.9.5.txt` | 171 | `b1d1662171fc97bd3b645285b770ea9fe3b2f9615300d0e84dec0226b3c996d9` |

Publication uses a GitHub **prerelease** at `v0.9.5`. The uploaded assets' names, sizes, and GitHub SHA-256 digests must match this table before publishing the draft. The source tag points at the merged release PR; older releases are retained.

Local evidence: `.build_tools/release-0.9.5-*.log`, `.build_tools/release-0.9.5-source-match.json`, `.build_tools/smoke-0.9.5/`, and `.build_tools/startup-0.9.5/`. Build outputs and test data are excluded from Git.

## Limits

- RAW fixtures test file matching/copying, not real-camera RAW decoding or large SD-card performance.
- Lightroom/Evoto XMP interpretation remains unverified.
- The installer is built for distribution; fresh installation, uninstall, and upgrade are not part of this validation.
- Packaged GUI interaction and high-DPI visual checks were not completed. Source tests cover Tk/Qt lifecycle, cancellation, result persistence, and relevant keyboard behavior.
- The EXEs are unsigned and the release remains a beta.
