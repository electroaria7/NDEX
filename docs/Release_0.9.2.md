# NDEX 0.9.2 Beta release validation

- Runtime/package source: `71aadbd` (release documentation may follow this commit).
- Windows, Python 3.12.10, pinned dependencies, PyInstaller 6.11.1, Inno Setup 6.7.3.
- All five EXEs rebuilt; 367 local tests and Windows CI on Python 3.10/3.12 passed.
- Portable and installed EXE smoke checks passed: SHA-256 backup verification, image catalog scan, RAW-name matching/copy/XMP generation, Frame export dimensions/ICC/copyright/GPS removal, and original preservation.
- ZIP integrity checked. Installer registered NDEX 0.9.2 Beta / version 0.9.2. Installation and uninstallation both exited 0 without reboot; test installation directory and uninstall registry entry were removed.
- Launcher scrolling and footer visibility were verified on the same UI source before the version-only release update (PR #16).

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| NDEX_Setup_0.9.2.exe | 626383799 | baee935e85803712792bf1cb78d9f3ffeeba4467643fea9965ada7abf96dfc56 |
| NDEX_v0.9.2.zip | 622502406 | f021381688df66b44247d2d3fafd243ed9b425cc45ab1277f47e4cd06079539b |

Local evidence is retained under `.build_tools`: `release-0.9.2-build.log`, `smoke-0.9.2/result.json`, `installed-smoke-0.9.2/result.json`, `install-0.9.2.log`, and `uninstall-0.9.2.log`.

This remains a public beta. RAW fixtures validate matching, not real camera decoding. Lightroom/Evoto interpretation of XMP and upgrades from earlier installations were not tested. Existing 1.0.1 installations should be removed first as documented in the README.
