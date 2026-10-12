# NDEX 0.9.6: XMP, upgrade, desktop UI and portrait RAW follow-up

Validation date: 2026-10-11 (America/Chicago; evidence timestamps also use UTC on October 12).
This supplements the [original release validation](Release_Validation_0.9.6.md).
The existing portable EXEs were tested without rebuilding them. The user then completed an in-place
0.9.3 → 0.9.6 installation, followed by installed-file, settings, shortcut and GUI-launch checks.

## Status

| Area | Result | Remaining work |
| --- | --- | --- |
| Packaged desktop interaction | Launcher, One, Image Manager, Auto Selector and Frame exercised through visible windows and mouse input | Full interaction regression, cancellation and error paths were not repeated |
| High DPI | Main workflows usable on one 2880×1800 display at 200% (1440×900 logical; 1440×852 available) | Other scales, mixed-DPI monitors and moving windows between monitors |
| Real portrait RAW | Unmodified Canon CR2 and Nikon NEF displayed upright in packaged Image Manager, including grid thumbnails | Portrait CR3/ARW/CRW/SRF/SR2/NRW and other cameras |
| XMP interoperability | ExifTool parsed the GUI exports; Evoto 7.3.5 read RAW ratings and external changes; standard `Red` mapped to red | Lightroom, JPEG/DNG sidecars and keyword use remain unverified; NDEX custom label/Pick do not become Evoto color/flag |
| Existing-install upgrade | 0.9.3 → 0.9.6 passed: all 14 payload files match, seven shortcuts resolve, all five installed apps open, original settings preserved | Other starting versions, fresh install and uninstall were not tested |

## Packaged mouse interaction at 200%

Tests used `release/NDEX_v0.9.6/`, disposable sample folders and an isolated `LOCALAPPDATA`.
The live user's settings file remained byte-for-byte unchanged after the portable-app tests.
Native file dialogs also used keyboard text entry; these were interactive GUI tests, not the headless
smoke-test entry points. Some apps were started with source/destination command-line arguments.

| Application | Actions and observed result |
| --- | --- |
| Launcher | Clicked Select & Rate; the packaged Image Manager opened |
| Image Manager | Chose the two-RAW folder, viewed both portraits, clicked Pick on the Canon and four stars on the Nikon, used File → Write XMP Sidecars: 2 written, 0 errors; switched to grid and checked both thumbnails |
| One | Selected Canon/Nikon RAW and Full check (every byte), clicked Analyze, Start Backup and confirmation: 2 copied and verified, 0 skipped, 0 errors; independent SHA-256 comparisons also matched |
| Auto Selector | Clicked Analyze Matches, then Copy RAW Files: 2 matches, 2 RAWs and 2 XMPs copied, 0 errors; RAW SHA-256 values matched the source |
| Frame | Used JPEGs extracted from the RAW previews, changed photo size, chose output folder, clicked Export All and confirmed: 2 JPEGs, both 1080×1440 with ICC profiles |

The controls and completion dialogs used in these workflows were visible and operable at 200%.
This establishes a single-display workflow check, not coverage of every dialog, minimum window size,
scale factor or monitor arrangement. The test JPEGs are extracted previews, not camera-produced RAW+JPEG pairs.

## Real portrait samples

Both files came from raw.pixls.us, whose repository records mark them CC0 1.0. Downloaded bytes matched
the repository SHA-256 values. No orientation tags were synthesized or changed. Both embedded JPEGs
had no orientation tag of their own, exercising the RAW-orientation fallback in the actual package.

| Camera | Original file | RAW orientation | Embedded JPEG | NDEX displayed proxy |
| --- | --- | ---: | --- | --- |
| Canon EOS Kiss Digital N | [20170226_0040.CR2](https://raw.pixls.us/getfile.php/1185/nice/Canon%20-%20EOS%20Kiss%20Digital%20N%20-%20RAW%20%283:2%29.CR2) | 8 (90° counterclockwise) | 1536×1024 | 1024×1536, upright lighthouse |
| Nikon Df | [DSC_6793_Df12uncompr.NEF](https://raw.pixls.us/getfile.php/1385/nice/Nikon%20-%20Df%20-%2012bit%2012bit%20uncompressed%20%283:2%29.NEF) | 6 (90° clockwise) | 4928×3280 | 3280×4928, upright plant/desk scene |

SHA-256:

```text
49c78e5c36255cdd3f9fd219e86e3325bfa67be4d8d1ab5e21c21c3fd53c294e  canon_kiss_n_portrait.CR2
38ea7aba6b7e0cdbd338fe6703d3c98291f4a9a28b0d1a81bfb1f77b21712c63  nikon_df_portrait.NEF
```

Source-code extraction and the packaged GUI produced the same dimensions. The packaged loupe and grid
were visually inspected, and source RAW hashes remained unchanged. The focused test run passed all 25
tests, including the optional real-sample path with these two files; that optional test alone checks
metadata/type/preview availability, not visual uprightness.

## What the XMP contains, and what external editors still need to prove

The shared writer stores `xmp:Rating`, `xmp:Label`, `xmp:MetadataDate` and `dc:subject` keywords.
It never modifies the photo itself. The actual packaged GUI produced:

| Producer / sample | Rating | Label | Keyword |
| --- | ---: | --- | --- |
| Image Manager / Canon Pick | 0 | `NDEX Selected` | `NDEX Pick` |
| Image Manager / Nikon four stars | 4 | absent | absent |
| Auto Selector / each copied RAW | 5 | `NDEX Selected` | `NDEX Selected` |

ExifTool independently parsed these values. NDEX's Pick/Maybe/Reject export uses keywords (and a label
for Pick); it does not write an editor-native pick-flag property. A `NDEX Pick` keyword is therefore
not evidence that another editor's Pick flag will be set. `NDEX Selected` is label text, not a guaranteed
red/green color assignment.

### Lightroom Classic

Adobe documents sidecars for proprietary RAW, but embedded XMP for JPEG, TIFF, PSD and DNG. NDEX writes
`<stem>.xmp` for all its RAW extensions, including DNG, and `<filename>.JPG.xmp` for JPEG to keep paired
files separate. The JPEG and DNG sidecar rules must not be advertised as proven Adobe interoperability.
See [Adobe metadata basics](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/metadata-basics-actions.html).

For an already imported image, use Metadata → Read Metadata From File to test external changes.
Automatically writing catalog changes to XMP is the opposite direction. Use disposable images and a
test catalog for this check. See [Adobe external metadata actions](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/advanced-metadata-actions.html).

Color labels depend on the configured label text. Classic 13.2 and later can save flags to XMP, so the
limitation here is NDEX's current export mapping, not a claim that Lightroom cannot store flags.
See [Adobe flags, labels and ratings](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/flag-label-rate-photos.html).

No Lightroom installation was found in the inspected application/install lists. The user's Lightroom
product and executable location are pending; these Classic instructions do not establish behavior in
the cloud-based Lightroom product.

### Evoto

The [official Library guide](https://support.evoto.ai/library/) describes XMP metadata import/export
and folder refresh for externally changed ratings, flags, color labels and EXIF/IPTC. It does not
prove how NDEX's exact label text and keywords are interpreted in every Evoto version.

The initial Evoto 7.0.5.0 session stopped at login. After the user logged in, both the executable version
and the in-app new-features dialog reported **7.3.5** (7.3.5.0 / V7.3.5-185). No update installation
was triggered by the agent. The following results apply to 7.3.5, not to the earlier 7.0.5 session.

A local project named `NDEX XMP Validation 0.9.6` was created, with device sync and smart photo analysis
off. Only copies in `evoto-input/manager/` were imported; the original GUI-generated evidence was retained.
Evoto detected external adjustments on import and the test accepted reading them, leaving automatic
XMP-profile import unchecked.

| Input / action | Observed Evoto 7.3.5 result |
| --- | --- |
| Image Manager Canon XMP: rating 0, label `NDEX Selected`, keyword `NDEX Pick` | No stars; context menus explicitly checked **No flag** and **No color label** |
| Image Manager Nikon XMP: rating 4 | Four stars in the grid; both portrait RAWs upright |
| Change only the disposable Canon XMP via the NDEX writer to rating 3, label `Red`; right-click → Read Metadata From File → confirm | Success message, three stars and red color label |
| Replace that disposable Canon sidecar with the packaged Auto Selector's original XMP (rating 5, label/keyword `NDEX Selected`); read metadata again | Success message, five stars; the previous red label disappeared |

Thus RAW-sidecar ratings and explicit re-reading passed. The custom `NDEX Selected` label does not
map to an Evoto color, and `NDEX Pick` does not set the native Pick flag. This is a concrete export-mapping
limitation, not a failure to find the RAW sidecar. Keyword interpretation remains unverified: the inspected
metadata panels did not expose a keyword field. No JPEG/DNG sidecar, folder-refresh command, Evoto-to-NDEX
round trip, or develop-setting compatibility was tested. Existing user projects were not edited.

## Upgrade from the existing 0.9.3 installation

The original install was `C:\Program Files (x86)\NDEX`, registered as 0.9.3, with version 0.9.3 in all
five EXEs. The current installer uses the same AppId
`{8F2C4A91-6D3E-4B17-9C58-1A7E0F4B2D90}` and requires administrator privileges.

The old installation and the live settings file were backed up locally. A copy of the old settings
was loaded and updated with 0.9.6 source code: all 15 original top-level keys survived, with no changed
original values or unrelated keys. This is a settings-compatibility check, not an installer-upgrade pass.

`NDEX_Setup_0.9.6.exe` matches the published validation hash
`d87daaf99b17c3f15ca18b5464b6012e1441f4bae0d290304d10e0caa8f9a17c`.
Two agent-initiated elevation requests returned cancellation without creating installation logs. The
user subsequently ran the installer directly and reported completion. No elevation bypass was used.
The resulting **in-place upgrade passed** these checks:

| Check | Result |
| --- | --- |
| Installation registration | Same install directory and AppId; `DisplayName = NDEX 0.9.6 Beta`, `DisplayVersion = 0.9.6` |
| Installed payload | All 14 release payload files, including all five EXEs, match `release/NDEX_v0.9.6` by SHA-256 |
| Settings immediately after install / Launcher startup | Byte-for-byte identical to the backed-up 0.9.3 settings |
| Shortcuts | Six Start Menu links (five apps and Docs) plus the desktop NDEX link point to existing targets inside the installed directory |
| Installed Launcher routing | Clicked all four app cards; One, Image Manager, Auto Selector and Frame opened from `C:\Program Files (x86)\NDEX\Apps`, not the portable folder |
| Settings after launching and closing the four apps | All 15 original top-level keys and their complete values preserved; only a new `shared` state section was added |
| Cleanup | The four test-launched child apps closed normally; the user's installed Launcher remained open |

The installed-app check covered startup and routing. Frame's Continue action restored an existing
workspace with a pre-existing file warning; no export or photo change was performed on that workspace.
Functional photo workflows were tested earlier with disposable data
in the byte-identical portable package. Fresh installation, uninstall and upgrades from versions other
than this existing 0.9.3 install remain unverified.

## Local evidence

Evidence is under `release/validation-0.9.6-followup/` (ignored by Git). Do not publish the copied live
settings or installation backup. This document records the shareable findings without those private files.

- `screenshots/`: Manager Canon/Nikon previews, XMP completion and grid; One backup; Auto Selector copy; Frame export.
- `portrait-manifest.json`, `portrait-results.json`, `packaged-portrait-results.json`: sample provenance, hashes and preview measurements.
- `manager-xmp-exiftool.json`, `selector-xmp-exiftool.json`: independently read GUI-generated XMP.
- `evoto-result.json` and `screenshots/evoto-*.png`: 7.3.5 import/re-read results. Evoto screenshots include the existing project sidebar and should remain private local evidence.
- `one-gui-result.json`, `frame-gui-result.json`, `display.json`, `focused-tests.log`: output checks and display/test scope.
- `installed-vs-portable.json`, `install-before.json`, `settings-migration-result.json`, `upgrade-attempt-result.json`: installation inventory, copied-settings check and canceled elevation result.
- `install-after.json`, `upgrade-installed-result.json`, `upgrade-shortcuts.json`, `upgrade-settings-after-gui.json`, `upgrade-gui-windows.json` and `screenshots/installed-*.png`: successful 0.9.3 → 0.9.6 upgrade evidence.

No application behavior was changed for this follow-up. The previously built/uploaded release assets
were not repackaged; their bundled documentation reflects the original validation snapshot.
