# NDEX 0.9.4 Beta — rebuild and release validation

Validation date: 2026-10-10. Release: [v0.9.4](https://github.com/electroaria7/NDEX/releases/tag/v0.9.4). Source changes: [PR #20](https://github.com/electroaria7/NDEX/pull/20).

## Build provenance

- Windows x64, isolated Python 3.12.10 virtual environment at `.build_tools/release-0.9.4-venv`; system site packages disabled.
- Runtime dependencies installed from `requirements.lock`: Pillow 12.3.0, PySide6 / Addons / Essentials / shiboken6 6.11.2. `pip check` passed.
- PyInstaller 6.11.1 and Inno Setup 6.7.3. `build_all.ps1 -Installer` completed successfully, rebuilding all five apps into a new `release/NDEX_v0.9.4` directory and compiling the installer.
- EXE build source: `1f6c06af58175c0ffbb2f2feea77f57a3c3d68ac`. Subsequent source changes only normalize two Windows test expectations and update documentation; application code is unchanged. After correcting packaged README links, `build_all.ps1 -SkipBuild -Installer` reassembled the final documentation and installer using the verified EXEs.
- Static inspection of all five EXEs found `NDEX_VERSION = "0.9.4"` and `NDEX_CHANNEL = "beta"`. Installer PE ProductVersion is `0.9.4`.
- A separate reviewer compared bundled repository Python code objects with current source: One 31, Manager 37, Selector 29, Launcher 25 modules match; Frame has 63 modules, with only two bundled test modules differing after the short-path test correction. All application modules match. Manager's new `operations.py`, and One/Manager's ExifTool and Perl runtime, are present.

Build warnings concern unused Qt SQL client DLLs (`fbclient.dll`, `MIMAPI64.dll`, `OCI.dll`, `LIBPQ.dll`), PySide deployment tooling (`project_lib`), and an optional `pkg_resources` hidden import. PyInstaller's QtQml hook also logged a warning-formatting `TypeError` for an unused QML plugin; NDEX Frame uses Qt Core/Gui/Widgets and does not import QML. No build step failed. Packaged startup and image export completed without stderr or crash logs; this does not validate those unused optional integrations. Compared with 0.9.3, the isolated environment excludes unused NumPy/OpenBLAS and YAML binaries; this accounts for much of the smaller package size.

## Automated source checks

| Suite | Passed |
| --- | ---: |
| Common / One / integration | 204 |
| Image Manager | 29 |
| Auto Selector | 54 |
| Launcher | 14 |
| Frame | 171 |
| **Total** | **472** |

All suites passed in the isolated Python 3.12.10 environment. [GitHub Actions run 38035260924](https://github.com/electroaria7/NDEX/actions/runs/38035260924) also passed the same suites on Windows with Python 3.10 and 3.12. The first CI run exposed two test expectations comparing unresolved Windows short temporary paths with resolved application paths; commit `d574857` corrects the expectations without changing application behavior.

Source tests exercise real Tk and Qt event loops for progress, cancellation, worker completion, safe closing and result persistence. See [the improvement review](Improvement_Review_2026-10-10.md) for the UI and efficiency evidence.

## Packaged EXE checks

`tests/smoke_release.py` ran against the newly built release folder with temporary settings and Korean folder/file names. All five command invocations exited with code 0 and empty stderr:

1. **One:** backed up two JPEG and two synthetic CR3 fixtures, verified SHA-256 and manifest records, and used the JPEG capture date for date folders. Original hashes were unchanged.
2. **Manager:** scanned the backup into a four-record catalog.
3. **Selector, first run:** copied two matching RAW fixtures and created two XMP sidecars while preserving unrelated destination files.
4. **Selector, repeated rename run:** copied 0, skipped 2, failed 0. All six destination RAW/XMP hashes, including a user-edited sidecar, remained unchanged despite different requested XMP values. No extra numbered copies appeared.
5. **Frame:** exported a Korean-named JPEG to 1080 × 1440, preserving ICC and copyright metadata and stripping GPS. Exported 1, failed 0; source hash unchanged.

Launcher has no corresponding file-processing CLI step. All five EXEs, including Launcher, separately survived at least 30 seconds of hidden startup using isolated empty workspaces and settings. Stderr and crash logs were empty. Only these test process trees were terminated afterward. This is a startup check, not interactive GUI or graceful-close validation of the packaged apps.

Local evidence is retained under `.build_tools/smoke-0.9.4/`, `.build_tools/startup-0.9.4/`, and `.build_tools/release-0.9.4-*.log`. Build outputs and temporary test data are excluded from Git.

## Distribution integrity

The release folder contains 14 files: five EXEs, eight documentation/legal files, and `SHA256SUMS.txt`. All 13 entries in the internal checksum manifest match, with no extra unlisted payload files. The installer compile log includes all 14 files.

The portable ZIP contains the same `NDEX_v0.9.4/` layout. ZIP CRC validation and SHA-256 comparison of every listed payload file passed. The separate `SHA256SUMS-0.9.4.txt` covers the installer and ZIP.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `NDEX_Setup_0.9.4.exe` | 522087388 | `6c6f1201ed435b42391a1a43aa5fb769afd9e457e15b795d292b5d82b6204ba6` |
| `NDEX_v0.9.4.zip` | 518477996 | `2f3c233667020199f40f26ba961ef5bdaa4a4f015b801d2df70cd5c8d92d9c89` |
| `SHA256SUMS-0.9.4.txt` | 171 | `300c81115fee251cddbc40a563808c21cf8ff10e3c7e768c903a17fce7102369` |

Publication uses a GitHub **prerelease** for tag `v0.9.4`; prior releases remain available. Uploaded asset sizes and GitHub SHA-256 digests must match this table before the draft is published. Source is committed to Git; binaries are release assets.

## Limits

- RAW fixtures test matching and copying, not decoding real camera RAWs or performance on large SD-card libraries.
- Lightroom/Evoto interpretation of XMP, real-camera image quality, and long-running workload benchmarks remain unverified.
- The installer was compiled and its metadata/input payload inspected. A fresh installation, uninstall, and upgrade were not executed on this machine. Historical installation checks do not count as 0.9.4 validation.
- Packaged GUI interaction and close/cancel behavior were not manually replayed; those behaviors have source-level event-loop regression coverage.
- EXEs remain unsigned. This is a beta release.
