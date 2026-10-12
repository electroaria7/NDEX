# RAW compatibility

NDEX reads camera RAW files through the bundled ExifTool (`vendor/exiftool`, v13.55 when measured).
It never decodes RAW pixel data: dates and metadata come from EXIF/maker notes, and previews are the
JPEG that the camera embeds in the RAW file.

The set of RAW extensions is defined once in `ndex_common/raw_formats.py`. NDEX One, Image Manager,
Auto Selector and the XMP writer all build their lists from it.

| Extension | Brand | Notes |
| --- | --- | --- |
| `.cr3` | Canon | EOS R/M series and newer |
| `.cr2` | Canon | EOS DSLR generation up to about 2018 |
| `.crw` | Canon | Pre-2004 PowerShot/D30/D60 (new in 0.9.6) |
| `.arw` | Sony | Alpha, NEX, ILCE, including lossless/compressed/uncompressed variants |
| `.srf` | Sony | DSC-F707/F717/F828, DSLR-A100 era |
| `.sr2` | Sony | DSC-R1, RX1/RX10 era |
| `.nef`, `.nrw` | Nikon | DSLR/Z and Coolpix |
| `.dng` | Adobe | Image Manager, Auto Selector and XMP only; NDEX One has no DNG checkbox yet |

NDEX One keeps the existing type folder names (`cr3`, `cr2`, `arw`, `srf`, `sr2`, `nef`, `nrw`). The new
`crw` type uses a lower-case `crw` folder and sits under the Canon checkbox.

## Test method

Samples were downloaded to `%TEMP%\ndex_raw\samples\` (not committed, treated as untrusted data, never
executed). A throwaway harness ran every file through the real NDEX code paths:

- **Date**: `src/metadata.py` `MetadataExtractor.get_capture_datetime` (NDEX One).
- **Type**: `src/file_types.py` `get_file_type_for_path` and the brand checkbox it belongs to.
- **Metadata**: Image Manager `MetadataReader.read_batch` (camera, lens, exposure, size).
- **Preview**: `CacheManager.ensure_display_assets` (embedded preview extraction, then thumbnail).
- **XMP**: `ndex_common.xmp.sidecar_path_for` and `write_xmp_sidecar`.
- **Auto Selector**: RAW index plus `_match_details` for `DSC01234.<ext>` / `IMG_1234.<ext>` with a JPG of the same stem.
- **Backup**: `execute_backup` (copy plus SHA-256 verify) into `YYYY/MM/MMDD/<type>/`.

The same checks run as an optional test: set `NDEX_RAW_SAMPLES` to a folder of RAW files and run
`tests/test_raw_compat.py` (it asserts an ExifTool date, a known type, and an embedded preview of at least
512 px for every file).

## Results (after the 0.9.6 changes)

All files: date read by ExifTool (not the fallback), metadata read, XMP sidecar written as `<stem>.xmp`,
Auto Selector matched the JPG pair, and the backup copy verified by SHA-256.

| Camera / format | Sample | NDEX One type (brand) | Capture date | Camera / lens read | Preview used | Preview size |
| --- | --- | --- | --- | --- | --- | --- |
| Canon EOS R, CR3 (C-RAW) | `canon_eos_r.CR3` | cr3 (Canon) | 2021-05-11 09:32:38 | yes / zoom range only | JpgFromRaw | 4176x2784 |
| Canon EOS R6, CR3 (C-RAW) | `canon_eos_r6.CR3` | cr3 (Canon) | 2021-05-12 12:21:21 | yes / RF70-200 | JpgFromRaw | 3408x2272 |
| Canon EOS M50, CR3 (C-RAW) | `canon_eos_m50.CR3` | cr3 (Canon) | 2021-05-10 20:11:06 | yes / EF-M18-150 | JpgFromRaw | 6000x4000 |
| Canon EOS 350D, CR2 | `canon_350d.CR2` | cr2 (Canon) | 2008-05-23 14:51:02 | yes / yes | PreviewImage | 3456x2304 |
| Canon EOS 600D, CR2 | `canon_600d.CR2` | cr2 (Canon) | 2017-07-14 08:39:52 | yes / Tamron 90mm | PreviewImage | 5184x3456 |
| Canon EOS 5D Mark II, CR2 (sRAW2) | `canon_5dm2_sraw.CR2` | cr2 (Canon) | 2017-07-20 14:31:40 | yes / 28-70mm | PreviewImage | 5616x3744 |
| Canon EOS 7D, CR2 (sRAW) | `canon_7d_sraw.CR2` | cr2 (Canon) | 2016-12-22 20:02:04 | yes / EF-S15-85 | PreviewImage | 5184x3456 |
| Canon PowerShot G1, CRW | `canon_g1.CRW` | crw (Canon) | 2003-10-08 06:22:52 | yes / zoom range | JpgFromRaw | 640x480 |
| Sony DSLR-A100, ARW | `sony_a100.ARW` | arw (Sony) | 2018-02-19 17:55:25 | yes / Minolta 18-70 | PreviewImage | 640x480 |
| Sony DSLR-A700, ARW | `sony_a700.ARW` | arw (Sony) | 2014-04-18 15:53:21 | yes / Sony 50mm | PreviewImage | 1616x1080 |
| Sony NEX-5, ARW | `sony_nex5.ARW` | arw (Sony) | 2015-09-24 09:28:02 | yes / E 18-55 | PreviewImage | 1616x1080 |
| Sony A7 (ILCE-7), ARW uncompressed | `sony_a7_uncompressed.ARW` | arw (Sony) | 2015-10-17 17:43:25 | yes / FE 28-70 | PreviewImage | 1616x1080 |
| Sony A7 IV, ARW lossless small | `sony_a7m4_lossless_small.ARW` | arw (Sony) | 2023-10-19 16:15:00 | yes / FE 50mm | JpgFromRaw | 3504x2336 |
| Sony A7 IV, ARW compressed | `sony_a7m4_compressed.ARW` | arw (Sony) | 2023-10-19 16:15:24 | yes / FE 50mm | JpgFromRaw | 7008x4672 |
| Sony A1 II, ARW lossless small APS-C | `sony_a1m2_lossless_small.ARW` | arw (Sony) | 2025-05-09 09:36:19 | yes / FE 70-200 | JpgFromRaw | 4320x2880 |
| Sony DSC-R1, SR2 | `sony_r1.SR2` | sr2 (Sony) | 2019-06-17 18:45:07 | yes / no lens tag (fixed lens) | PreviewImage | 640x424 |
| Sony DSC-F828, SRF | `sony_f828.SRF` | srf (Sony) | 2017-03-27 15:02:34 | yes / no lens tag (fixed lens) | ThumbnailImage (only one present) | 640x480 |
| Nikon D70, NEF | `nikon_d70.NEF` | nef (Nikon) | 2017-09-02 16:55:01 | yes / 50mm f/1.8 | JpgFromRaw | 3008x2000 |
| Nikon Coolpix P330, NRW | `nikon_p330.NRW` | nrw (Nikon) | 2017-01-16 22:38:56 | yes / no lens tag (fixed lens) | JpgFromRaw | 4000x3000 |

### Before and after

The type, date, metadata, XMP naming, Auto Selector and backup columns were already correct for CR3, CR2,
ARW, SRF, SR2, NEF and NRW. What changed:

| Item | Before | After |
| --- | --- | --- |
| Canon CRW (`.crw`) | Not a known type in NDEX One (listed as `others`, no checkbox); sidecar named `IMG.CRW.xmp`; Auto Selector reported no match | `crw` type under the Canon checkbox; sidecar `IMG.xmp`; Auto Selector matches |
| DNG (`.dng`) in Auto Selector | Not matched | Matched (list is now shared) |
| Canon CR3 preview | 1620x1080 `PreviewImage` | full size from `JpgFromRaw` (3408x2272 to 6000x4000) |
| Nikon D70 NEF preview | 564x372 | 3008x2000 |
| Nikon Coolpix NRW preview | 640x480 | 4000x3000 (P330) |
| Sony A7 IV ARW preview | 1616x1080 | 3504x2336 to 7008x4672 |
| Sony A1 II ARW preview | 1616x1080 | 4320x2880 |
| Orientation | A preview without its own EXIF orientation tag showed portrait shots sideways | The RAW file's orientation is baked into the preview when the embedded JPEG has no tag of its own |
| Preview fallback | Fixed order PreviewImage, JpgFromRaw, ThumbnailImage; the first tag wins even when tiny | All tags are sized first, then tried largest to smallest; a corrupt or non-JPEG candidate falls through to the next |

Unchanged previews (the camera embeds only a small JPEG): Sony A700/NEX-5/A7 stay at 1616x1080; Sony
A100, DSC-R1, DSC-F828 and Canon CRW stay at 640x480 or smaller.

## Samples and licenses

All samples come from the raw.pixls.us repository (`https://raw.pixls.us/data/<Make>/<Model>/<file>`),
which publishes camera samples under CC0 1.0 (Public Domain Dedication) unless marked otherwise. The
license of every file below was checked against `https://raw.pixls.us/json/getrepository.php?set=all`.
Two other samples in the repository (Canon PowerShot S30 CRW and Nikon Coolpix P7000 NRW) are CC BY-NC-SA 4.0,
so they were not used.

| Sample | Source file | License |
| --- | --- | --- |
| `canon_eos_r.CR3` | `Canon/EOS R/Canon_EOS_R_CRAW_ISO_100_crop_nodual.CR3` | CC0 1.0 |
| `canon_eos_r6.CR3` | `Canon/EOS R6/Canon_EOS_R6_CRAW_ISO_100_crop_nodual.CR3` | CC0 1.0 |
| `canon_eos_m50.CR3` | `Canon/EOS M50/Canon_EOS_M50_CRAW_ISO_100_nocrop_nodual.CR3` | CC0 1.0 |
| `canon_350d.CR2` | `Canon/EOS 350D/IMG_1707.CR2` | CC0 1.0 |
| `canon_600d.CR2` | `Canon/EOS 600D/_MG_2587.CR2` | CC0 1.0 |
| `canon_5dm2_sraw.CR2` | `Canon/EOS 5D Mark II/10.canon.sraw2.cr2` | CC0 1.0 |
| `canon_7d_sraw.CR2` | `Canon/EOS 7D/RAW_CANON_EOS_7D-sraw.CR2` | CC0 1.0 |
| `canon_g1.CRW` | `Canon/PowerShot G1/crw_1693.crw` | CC0 1.0 |
| `sony_a100.ARW` | `Sony/DSLR-A100/_DSC0258.ARW` | CC0 1.0 |
| `sony_a700.ARW` | `Sony/DSLR-A700/DSC07249.ARW` | CC0 1.0 |
| `sony_nex5.ARW` | `Sony/NEX-5/20150924T092802_Château_Schönbrunn_AT.ARW` | CC0 1.0 |
| `sony_a7_uncompressed.ARW` | `Sony/ILCE-7/Sony_-_ILCE-7_-_14bit_uncompressed_(32).arw` | CC0 1.0 |
| `sony_a7m4_lossless_small.ARW` | `Sony/ILCE-7M4/ILCE-7M4_DSC06676_FullFrame-LossLess-Compressed-Small.ARW` | CC0 1.0 |
| `sony_a7m4_compressed.ARW` | `Sony/ILCE-7M4/ILCE-7M4_DSC06677_FullFrame-Raw-Compressed.ARW` | CC0 1.0 |
| `sony_a1m2_lossless_small.ARW` | `SONY/ILCE-1M2/A1_07633_lossless_compressed_small_apsc.ARW` | CC0 1.0 |
| `sony_r1.SR2` | `Sony/DSC-R1/_DSC1477.SR2` | CC0 1.0 |
| `sony_f828.SRF` | `Sony/DSC-F828/DSC06227.SRF` | CC0 1.0 |
| `nikon_d70.NEF` | `Nikon/D70/20170902_0047.NEF` | CC0 1.0 |
| `nikon_p330.NRW` | `Nikon/Coolpix P330/DSCN0138.NRW` | CC0 1.0 |

The RAW files themselves are not stored in this repository.

## Known limitations

- **Preview quality is whatever the camera embedded.** Many Sony bodies (A700, NEX, A7) only embed a
  1616x1080 JPEG, and A100, DSC-R1, DSC-F828 and CRW files only carry 640 px or smaller previews. Image
  Manager shows these as is and never renders the RAW data.
- **Only the largest embedded JPEG is used**, chosen by byte size. If a camera embeds a larger but lower
  quality JPEG next to a smaller good one, the larger one wins.
- **Orientation** is applied from the RAW file's EXIF `Orientation` when the preview has no tag of its
  own. The original 19 samples were landscape. A [follow-up with two unmodified portrait RAWs](Release_Validation_0.9.6_Followup.md#real-portrait-samples)
  verified Canon CR2 (orientation 8) and Nikon NEF (orientation 6), including upright loupe/grid display
  in the packaged app. Other portrait formats/cameras remain unverified; synthetic tests cover all eight orientations.
- **Canon sRAW/mRAW** files report the full sensor size as the image size in Image Manager (for example
  5616x3744 for a 5D Mark II sRAW2 whose real raw is 2784x1856).
- **Fixed-lens cameras** (DSC-R1, DSC-F828, Coolpix) have no lens model tag, so the lens column is empty.
- **NDEX Frame does not import RAW files.** It works on the JPG/exported output only.
- **DNG** is recognised by Image Manager, Auto Selector and the XMP writer but not by NDEX One (no brand
  checkbox). Adding it needs a new checkbox in `src/gui.py`.
- **Other brands** (Fujifilm RAF, Olympus ORF, Panasonic RW2, Pentax PEF and so on) are not supported.
- NDEX One's command-line `--types` default for a settings file written by an older version leaves `crw`
  off until the settings template lists it (`default_file_types` in `src/config.py` and
  `config/settings.json`); the GUI checkbox defaults to on.
