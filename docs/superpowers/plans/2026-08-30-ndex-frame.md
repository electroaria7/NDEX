# NDEX Frame v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `NDEX_Frame.exe` that previews and batch-exports crop-free, color-managed Instagram images from finished Master files.

**Architecture:** A Qt-independent core owns preset models, geometry, color conversion, rendering, and safe export. PySide6 provides a preview-first desktop UI over those services, while `ndex_common` supplies shared branding, paths, JSON persistence, settings, launching, and versioning.

**Tech Stack:** Python 3.10+, Pillow `>=10,<12`, PySide6 `>=6.8,<7`, LittleCMS through `PIL.ImageCms`, `unittest`, PyInstaller 6.11.1, PowerShell.

**Spec:** `docs/superpowers/specs/2026-08-30-ndex-frame-design.md`

## Global Constraints

- Product and executable names are `NDEX Frame` and `NDEX_Frame.exe`.
- The default Frame Preset is `White 3:4`; the default Output Profile is `Instagram Feed HQ`.
- The default Output Profile uses fixed width 1080px, JPEG Quality 95, 4:4:4 chroma, sRGB with embedded ICC, preserved capture/copyright metadata, and removed GPS.
- FIT is the only v0.1 fit mode; `photo_scale` is constrained to `0.10 <= scale <= 1.00` and must never crop.
- Preview and Export must consume the same `RenderPlan`; framing disagreement may not exceed one output pixel.
- Master files and existing outputs may not be overwritten. Every final output is written to a same-directory temporary file, verified, and renamed.
- Frame Preset and Output Profile defaults are independent and stored in the `frame` section of the shared NDEX settings file.
- Built-in presets are immutable. Editing one creates a custom copy.
- The first release supports JPG/JPEG, PNG, and TIFF input and JPEG, PNG, and WebP output.
- Core, imaging, preset, and export services may not import PySide6.
- Existing NDEX tests must remain green.
- The current workspace is not recognized as a Git repository. Restore or initialize the intended Git metadata before executing commit steps; do not create an unrelated repository merely to satisfy this plan.

---

## File Map

### New application files

- `ndex_frame/__init__.py` — package marker.
- `ndex_frame/__main__.py` — `python -m ndex_frame` entry point.
- `ndex_frame/main.py` — crash handler and PySide6 application startup.
- `ndex_frame/core/models.py` — immutable presets, sizing, overrides, source item, and render plan types.
- `ndex_frame/core/geometry.py` — output dimensions, FIT sizing, normalized positioning, and rounding.
- `ndex_frame/core/validation.py` — profile, source, destination, and batch validation.
- `ndex_frame/imaging/color.py` — EXIF orientation, ICC-to-sRGB conversion, and metadata sanitization.
- `ndex_frame/imaging/renderer.py` — Master-to-canvas rendering using a `RenderPlan`.
- `ndex_frame/imaging/encoders.py` — JPEG/PNG/WebP options and same-directory atomic save.
- `ndex_frame/services/presets.py` — built-in/custom preset persistence and independent defaults.
- `ndex_frame/services/importer.py` — file/folder discovery and source metadata.
- `ndex_frame/services/cache.py` — thumbnail/proxy cache keying and generation.
- `ndex_frame/services/export_job.py` — immutable job snapshots, collision planning, progress, cancellation, and results.
- `ndex_frame/ui/workspace.py` — in-memory workspace state and image overrides.
- `ndex_frame/ui/preview_widget.py` — scaled preview painting and drag-to-position conversion.
- `ndex_frame/ui/profile_dialog.py` — Output Profile editor with Advanced settings.
- `ndex_frame/ui/preset_dialog.py` — Frame Preset save/duplicate/default actions.
- `ndex_frame/ui/main_window.py` — approved preview-first single-window composition.
- `ndex_frame/resources/presets/frame/white-3x4.json` — immutable built-in Frame Preset.
- `ndex_frame/resources/presets/output/instagram-feed-hq.json` — immutable built-in Output Profile.
- `ndex_frame/build_package.ps1` — PyInstaller one-file Windows build.
- `ndex_frame/requirements.txt` — app runtime dependencies.
- `ndex_frame/tests/` — unit, integration, UI, and packaged-smoke tests.

### Existing files to modify

- `ndex_common/branding.py` — add `NDEX_FRAME_TITLE`.
- `ndex_common/settings.py` — register the `frame` settings namespace.
- `ndex_common/launch.py` — resolve `NDEX_Frame.exe` and the dev module.
- `ndex_launcher/state.py` — add the Frame workflow step after Auto Selector.
- `ndex_launcher/main.py` — render four responsive workflow cards.
- `ndex_launcher/tests/test_state.py` — verify the new workflow step.
- `requirements.txt` — add the PySide6 runtime range used by the root development environment.
- `build_all.ps1` — build and assemble the fifth executable.
- `release_README.md` — document NDEX Frame launch and basic workflow.
- `THIRD_PARTY_NOTICES.md` — add Qt/PySide6 and shiboken notices before distribution.
- `.gitignore` — ignore `.superpowers/` visual-companion artifacts and NDEX Frame build outputs.

---

### Task 1: Package, shared identity, dependencies, and immutable models

**Files:**
- Create: `ndex_frame/__init__.py`
- Create: `ndex_frame/core/__init__.py`
- Create: `ndex_frame/core/models.py`
- Create: `ndex_frame/tests/__init__.py`
- Create: `ndex_frame/tests/test_models.py`
- Create: `ndex_frame/requirements.txt`
- Modify: `requirements.txt`
- Modify: `ndex_common/branding.py`
- Modify: `ndex_common/settings.py`

**Interfaces:**
- Consumes: `ndex_common.settings.get_section(section, defaults)` and `update_section(section, values)`.
- Produces: `AspectRatio`, `OutputSizing`, `FramePreset`, `OutputProfile`, `ImageOverride`, `SourceItem`, `RenderPlan`, `NDEX_FRAME_TITLE`, and the settings section name `frame`.

- [ ] **Step 1: Write model validation tests**

```python
# ndex_frame/tests/test_models.py
import unittest
from pathlib import Path

from ndex_frame.core.models import AspectRatio, FramePreset, ImageOverride, OutputSizing


class ModelTests(unittest.TestCase):
    def test_ratio_rejects_non_positive_parts(self) -> None:
        with self.assertRaises(ValueError):
            AspectRatio(0, 4)

    def test_frame_scale_is_limited_to_fit_range(self) -> None:
        with self.assertRaises(ValueError):
            FramePreset("custom.bad", "Bad", 1, AspectRatio(3, 4), "#FFFFFF", 1.01, 0.0, 0.0, False)

    def test_fixed_width_requires_positive_width(self) -> None:
        with self.assertRaises(ValueError):
            OutputSizing(mode="fixed_width", width=0)

    def test_override_is_source_specific(self) -> None:
        override = ImageOverride(Path("IMG_001.jpg"), 0.9, 0.1, -0.2)
        self.assertEqual(override.photo_scale, 0.9)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the model test and verify the missing module failure**

Run: `python -m unittest ndex_frame.tests.test_models -v`  
Expected: `ModuleNotFoundError: No module named 'ndex_frame.core.models'`.

- [ ] **Step 3: Implement immutable model types**

```python
# ndex_frame/core/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SizingMode = Literal["fixed_width", "fixed_height", "long_edge", "fixed_dimensions"]
OutputFormat = Literal["jpeg", "png", "webp"]


@dataclass(frozen=True, slots=True)
class AspectRatio:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Aspect ratio parts must be positive.")


@dataclass(frozen=True, slots=True)
class OutputSizing:
    mode: SizingMode
    width: int | None = None
    height: int | None = None
    long_edge: int | None = None

    def __post_init__(self) -> None:
        values = {"fixed_width": self.width, "fixed_height": self.height, "long_edge": self.long_edge}
        if self.mode in values and (values[self.mode] is None or values[self.mode] <= 0):
            raise ValueError(f"{self.mode} requires a positive size.")
        if self.mode == "fixed_dimensions" and (
            self.width is None or self.width <= 0 or self.height is None or self.height <= 0
        ):
            raise ValueError("fixed_dimensions requires positive width and height.")


@dataclass(frozen=True, slots=True)
class FramePreset:
    id: str
    name: str
    version: int
    ratio: AspectRatio
    background: str
    photo_scale: float
    x: float
    y: float
    builtin: bool = False

    def __post_init__(self) -> None:
        if not 0.10 <= self.photo_scale <= 1.00:
            raise ValueError("photo_scale must be between 0.10 and 1.00.")


@dataclass(frozen=True, slots=True)
class MetadataPolicy:
    preserve_capture: bool = True
    preserve_copyright: bool = True
    remove_gps: bool = True


@dataclass(frozen=True, slots=True)
class OutputProfile:
    id: str
    name: str
    version: int
    sizing: OutputSizing
    format: OutputFormat
    quality: int
    chroma_subsampling: str
    color_space: str
    embed_icc: bool
    metadata: MetadataPolicy
    builtin: bool = False


@dataclass(frozen=True, slots=True)
class ImageOverride:
    source_path: Path
    photo_scale: float
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class SourceItem:
    path: Path
    oriented_width: int
    oriented_height: int
    has_icc: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RenderPlan:
    canvas_width: int
    canvas_height: int
    photo_width: int
    photo_height: int
    left: int
    top: int
```

- [ ] **Step 4: Add shared naming and dependency ranges**

Add `NDEX_FRAME_TITLE = "NDEX Frame"` beside the existing title constants. Add `"frame"` to `SECTION_KEYS`. Set both `requirements.txt` and `ndex_frame/requirements.txt` to include:

```text
Pillow>=10.0.0,<12.0.0
PySide6>=6.8.0,<7.0.0
```

- [ ] **Step 5: Run the focused and shared settings tests**

Run: `python -m unittest ndex_frame.tests.test_models tests.test_shared_settings -v`  
Expected: all tests pass.

- [ ] **Step 6: Commit the model boundary**

```powershell
git add ndex_frame requirements.txt ndex_common/branding.py ndex_common/settings.py
git commit -m "feat(frame): add immutable frame domain models"
```

---

### Task 2: Deterministic FIT geometry and shared RenderPlan

**Files:**
- Create: `ndex_frame/core/geometry.py`
- Create: `ndex_frame/tests/test_geometry.py`

**Interfaces:**
- Consumes: `AspectRatio`, `OutputSizing`, and `RenderPlan` from Task 1.
- Produces: `resolve_canvas(sizing, ratio) -> tuple[int, int]` and `build_render_plan(source_size, canvas_size, photo_scale, x, y) -> RenderPlan`.

- [ ] **Step 1: Write fixed-output and FIT tests**

```python
# ndex_frame/tests/test_geometry.py
import unittest

from ndex_frame.core.geometry import build_render_plan, resolve_canvas
from ndex_frame.core.models import AspectRatio, OutputSizing


class GeometryTests(unittest.TestCase):
    def test_fixed_width_3_by_4_is_1080_by_1440(self) -> None:
        size = resolve_canvas(OutputSizing("fixed_width", width=1080), AspectRatio(3, 4))
        self.assertEqual(size, (1080, 1440))

    def test_landscape_fits_without_crop(self) -> None:
        plan = build_render_plan((6000, 4000), (1080, 1440), 1.0, 0.0, 0.0)
        self.assertEqual((plan.photo_width, plan.photo_height), (1080, 720))
        self.assertEqual((plan.left, plan.top), (0, 360))

    def test_five_by_seven_portrait_gets_side_margins(self) -> None:
        plan = build_render_plan((5000, 7000), (1080, 1440), 1.0, 0.0, 0.0)
        self.assertEqual(plan.photo_height, 1440)
        self.assertEqual(plan.left, (1080 - plan.photo_width) // 2)

    def test_normalized_position_is_clamped_to_no_crop_bounds(self) -> None:
        plan = build_render_plan((6000, 4000), (1080, 1440), 1.0, 0.0, 2.0)
        self.assertEqual(plan.top + plan.photo_height, 1440)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify missing geometry functions**

Run: `python -m unittest ndex_frame.tests.test_geometry -v`  
Expected: import failure for `ndex_frame.core.geometry`.

- [ ] **Step 3: Implement canvas sizing with half-up rounding**

```python
from decimal import Decimal, ROUND_HALF_UP

from ndex_frame.core.models import AspectRatio, OutputSizing, RenderPlan


def _round(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def resolve_canvas(sizing: OutputSizing, ratio: AspectRatio) -> tuple[int, int]:
    if sizing.mode == "fixed_width":
        width = int(sizing.width)
        return width, _round(width * ratio.height / ratio.width)
    if sizing.mode == "fixed_height":
        height = int(sizing.height)
        return _round(height * ratio.width / ratio.height), height
    if sizing.mode == "fixed_dimensions":
        return int(sizing.width), int(sizing.height)
    edge = int(sizing.long_edge)
    if ratio.width >= ratio.height:
        return edge, _round(edge * ratio.height / ratio.width)
    return _round(edge * ratio.width / ratio.height), edge
```

- [ ] **Step 4: Implement FIT and normalized position clamping**

```python
def build_render_plan(
    source_size: tuple[int, int],
    canvas_size: tuple[int, int],
    photo_scale: float,
    x: float,
    y: float,
) -> RenderPlan:
    if not 0.10 <= photo_scale <= 1.00:
        raise ValueError("photo_scale must be between 0.10 and 1.00.")
    source_width, source_height = source_size
    canvas_width, canvas_height = canvas_size
    if min(source_width, source_height, canvas_width, canvas_height) <= 0:
        raise ValueError("Source and canvas dimensions must be positive.")

    fit = min(canvas_width / source_width, canvas_height / source_height) * photo_scale
    photo_width = max(1, min(canvas_width, _round(source_width * fit)))
    photo_height = max(1, min(canvas_height, _round(source_height * fit)))
    free_x = canvas_width - photo_width
    free_y = canvas_height - photo_height
    normalized_x = max(-1.0, min(1.0, x))
    normalized_y = max(-1.0, min(1.0, y))
    left = _round((free_x / 2) * (normalized_x + 1.0))
    top = _round((free_y / 2) * (normalized_y + 1.0))
    return RenderPlan(canvas_width, canvas_height, photo_width, photo_height, left, top)
```

- [ ] **Step 5: Run geometry tests and a 1px parity matrix**

Add a matrix test over source sizes `(3000, 4000)`, `(5000, 7000)`, `(6000, 4000)`, `(4000, 4000)` and preview widths `270`, `540`, `1080`. Scale preview coordinates back to output coordinates and assert every edge differs by at most one pixel.

Run: `python -m unittest ndex_frame.tests.test_geometry -v`  
Expected: all tests pass.

- [ ] **Step 6: Commit deterministic geometry**

```powershell
git add ndex_frame/core/geometry.py ndex_frame/tests/test_geometry.py
git commit -m "feat(frame): add crop-free render geometry"
```

---

### Task 3: Built-in presets, custom persistence, and independent defaults

**Files:**
- Create: `ndex_frame/resources/presets/frame/white-3x4.json`
- Create: `ndex_frame/resources/presets/output/instagram-feed-hq.json`
- Create: `ndex_frame/services/__init__.py`
- Create: `ndex_frame/services/presets.py`
- Create: `ndex_frame/tests/test_presets.py`

**Interfaces:**
- Consumes: model types from Task 1, `ndex_common.jsonio.write_json_atomic`, and `ndex_common.settings`.
- Produces: `PresetStore(root, settings_reader, settings_writer)`, `list_frames()`, `list_outputs()`, `save_frame()`, `save_output()`, `delete_custom()`, `set_default_frame()`, and `set_default_output()`.

- [ ] **Step 1: Add the exact built-in JSON resources**

```json
{
  "id": "builtin.white-3x4",
  "name": "White 3:4",
  "version": 1,
  "ratio": {"width": 3, "height": 4},
  "background": "#FFFFFF",
  "photo_scale": 1.0,
  "x": 0.0,
  "y": 0.0
}
```

```json
{
  "id": "builtin.instagram-feed-hq",
  "name": "Instagram Feed HQ",
  "version": 1,
  "sizing": {"mode": "fixed_width", "width": 1080},
  "format": "jpeg",
  "quality": 95,
  "chroma_subsampling": "4:4:4",
  "color_space": "sRGB",
  "embed_icc": true,
  "metadata": {"preserve_capture": true, "preserve_copyright": true, "remove_gps": true}
}
```

- [ ] **Step 2: Write persistence and immutability tests**

```python
def test_builtins_are_loaded_and_cannot_be_deleted(self) -> None:
    store = self.make_store()
    self.assertEqual(store.default_frame().id, "builtin.white-3x4")
    with self.assertRaises(ValueError):
        store.delete_custom("builtin.white-3x4", kind="frame")

def test_frame_and_output_defaults_are_independent(self) -> None:
    store = self.make_store()
    custom = replace(store.default_frame(), id="custom.tight", name="Tight", builtin=False)
    store.save_frame(custom)
    store.set_default_frame(custom.id)
    self.assertEqual(store.default_frame().id, "custom.tight")
    self.assertEqual(store.default_output().id, "builtin.instagram-feed-hq")
```

Use a temporary directory and injected dictionary-backed settings reader/writer so tests do not touch `%LOCALAPPDATA%`.

- [ ] **Step 3: Run tests and verify the service is missing**

Run: `python -m unittest ndex_frame.tests.test_presets -v`  
Expected: import failure for `PresetStore`.

- [ ] **Step 4: Implement strict JSON decoding and atomic custom writes**

Implement private decoders `_frame_from_dict(data, builtin)` and `_output_from_dict(data, builtin)` that construct Task 1 dataclasses and reject missing/invalid fields with `PresetError(path, message)`. Store custom presets as one JSON file per ID under:

```text
%LOCALAPPDATA%/NDEX/Frame/presets/frame/
%LOCALAPPDATA%/NDEX/Frame/presets/output/
```

Call `write_json_atomic()` for every custom save. Reject IDs beginning with `builtin.` in `save_frame()` and `save_output()`.

- [ ] **Step 5: Implement default fallback behavior**

Read `default_frame_id` and `default_output_id` from `get_section("frame", defaults)`. If a stored ID no longer exists, return the appropriate built-in and persist the repaired ID through `update_section("frame", values)`.

- [ ] **Step 6: Run preset tests**

Run: `python -m unittest ndex_frame.tests.test_presets -v`  
Expected: all tests pass, including corrupt custom JSON being reported without hiding valid presets.

- [ ] **Step 7: Commit preset persistence**

```powershell
git add ndex_frame/resources ndex_frame/services/presets.py ndex_frame/tests/test_presets.py
git commit -m "feat(frame): add independent frame and output presets"
```

---

### Task 4: Color-managed Master preparation and privacy-safe metadata

**Files:**
- Create: `ndex_frame/imaging/__init__.py`
- Create: `ndex_frame/imaging/color.py`
- Create: `ndex_frame/tests/fixtures/make_color_fixtures.py`
- Create: `ndex_frame/tests/fixtures/adobe-rgb-master.jpg`
- Create: `ndex_frame/tests/test_color.py`

**Interfaces:**
- Consumes: Pillow `Image`, `ImageCms`, `ImageOps`, and `MetadataPolicy`.
- Produces: `PreparedImage(image, icc_bytes, exif_bytes, warnings)`, `prepare_master(path, policy)`, and `srgb_profile_bytes()`.

- [ ] **Step 1: Create deterministic test fixtures in memory**

```python
from PIL import Image, ImageCms


def image_with_profile(profile_name: str) -> tuple[Image.Image, bytes]:
    image = Image.new("RGB", (40, 30), (140, 90, 40))
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile(profile_name))
    return image, profile.tobytes()
```

For Adobe RGB coverage, do not commit a standalone Adobe ICC profile. Adobe's profile license permits distribution embedded within a digital image, while bundling a standalone profile with software has additional terms: `https://www.adobe.com/support/downloads/iccprofiles/icc_eula_win_dist.html`.

`make_color_fixtures.py` accepts `--adobe-profile PATH`, creates a 32×32 RGB gradient, converts it into that profile, and saves `adobe-rgb-master.jpg` with the profile embedded. Generate it from an officially obtained Adobe RGB (1998) profile, commit only the JPEG fixture, and verify with Pillow that `icc_profile` exists before committing. Also generate a LAB-profile image in memory to cover the generic non-RGB transform error path.

- [ ] **Step 2: Write orientation, ICC, and GPS tests**

```python
def test_missing_icc_is_assumed_srgb_with_warning(self) -> None:
    prepared = prepare_master(self.no_icc_path, MetadataPolicy())
    self.assertEqual(prepared.image.mode, "RGB")
    self.assertIn("색상 프로필 없음", prepared.warnings)
    self.assertTrue(prepared.icc_bytes)

def test_gps_is_removed_but_copyright_remains(self) -> None:
    prepared = prepare_master(self.exif_path, MetadataPolicy(remove_gps=True))
    exif = Image.Exif()
    exif.load(prepared.exif_bytes)
    self.assertNotIn(34853, exif)
    self.assertEqual(exif.get(33432), "Joseph")
```

- [ ] **Step 3: Run tests and verify missing implementation**

Run: `python -m unittest ndex_frame.tests.test_color -v`  
Expected: import failure for `ndex_frame.imaging.color`.

- [ ] **Step 4: Implement orientation and ICC conversion**

```python
@dataclass(slots=True)
class PreparedImage:
    image: Image.Image
    icc_bytes: bytes
    exif_bytes: bytes
    warnings: tuple[str, ...]


def srgb_profile_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def prepare_master(path: Path, policy: MetadataPolicy) -> PreparedImage:
    with Image.open(path) as opened:
        source_exif = opened.getexif()
        oriented = ImageOps.exif_transpose(opened)
        source_icc = opened.info.get("icc_profile")
        warnings: list[str] = []
        if source_icc:
            source_profile = ImageCms.ImageCmsProfile(BytesIO(source_icc))
            target_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
            rgb = ImageCms.profileToProfile(oriented.convert("RGB"), source_profile, target_profile, outputMode="RGB")
        else:
            rgb = oriented.convert("RGB")
            warnings.append("색상 프로필 없음")
        exif_bytes = sanitize_exif(source_exif, policy)
        return PreparedImage(rgb.copy(), srgb_profile_bytes(), exif_bytes, tuple(warnings))
```

`sanitize_exif()` must delete orientation tag `274` after transposition and GPS tag `34853` when requested. Preserve capture-date tags and copyright tag `33432` according to `MetadataPolicy`.

- [ ] **Step 5: Run color tests and inspect saved bytes**

Run: `python -m unittest ndex_frame.tests.test_color -v`  
Expected: all tests pass; re-opening a saved test output reports an ICC profile and no GPS IFD.

- [ ] **Step 6: Commit color preparation**

```powershell
git add ndex_frame/imaging/color.py ndex_frame/tests/test_color.py ndex_frame/tests/fixtures
git commit -m "feat(frame): add color-managed master preparation"
```

---

### Task 5: Master rendering and format-specific atomic encoders

**Files:**
- Create: `ndex_frame/imaging/renderer.py`
- Create: `ndex_frame/imaging/encoders.py`
- Create: `ndex_frame/tests/test_renderer.py`
- Create: `ndex_frame/tests/test_encoders.py`

**Interfaces:**
- Consumes: `PreparedImage`, `RenderPlan`, `OutputProfile`.
- Produces: `render(prepared, plan, background) -> Image.Image`, `save_output_atomic(rendered, destination, profile, prepared) -> Path`, and `verify_output(path, profile, expected_size) -> None`.

- [ ] **Step 1: Write pixel-placement renderer tests**

```python
def test_renderer_places_photo_on_white_canvas(self) -> None:
    prepared = PreparedImage(Image.new("RGB", (6, 4), "red"), b"icc", b"", ())
    plan = RenderPlan(12, 16, 12, 8, 0, 4)
    rendered = render(prepared, plan, "#FFFFFF")
    self.assertEqual(rendered.size, (12, 16))
    self.assertEqual(rendered.getpixel((0, 0)), (255, 255, 255))
    self.assertEqual(rendered.getpixel((6, 8)), (255, 0, 0))
```

- [ ] **Step 2: Write JPEG profile and no-overwrite tests**

```python
def test_jpeg_is_444_and_contains_icc(self) -> None:
    result = save_output_atomic(self.image, self.destination, self.jpeg_profile, self.prepared)
    with Image.open(result) as reopened:
        self.assertEqual(reopened.size, (1080, 1440))
        self.assertTrue(reopened.info.get("icc_profile"))

def test_existing_destination_is_never_replaced(self) -> None:
    self.destination.write_bytes(b"existing")
    with self.assertRaises(FileExistsError):
        save_output_atomic(self.image, self.destination, self.jpeg_profile, self.prepared)
    self.assertEqual(self.destination.read_bytes(), b"existing")
```

- [ ] **Step 3: Run focused tests and verify missing functions**

Run: `python -m unittest ndex_frame.tests.test_renderer ndex_frame.tests.test_encoders -v`  
Expected: import failures for renderer and encoder functions.

- [ ] **Step 4: Implement one-pass rendering**

```python
def render(prepared: PreparedImage, plan: RenderPlan, background: str) -> Image.Image:
    canvas = Image.new("RGB", (plan.canvas_width, plan.canvas_height), background)
    resized = prepared.image.resize((plan.photo_width, plan.photo_height), Image.Resampling.LANCZOS)
    canvas.paste(resized, (plan.left, plan.top))
    return canvas
```

- [ ] **Step 5: Implement format-aware temporary writes**

Create the temporary file with a random name in `destination.parent`, open it with exclusive creation, and pass the file handle to Pillow so the temporary suffix does not determine format. Use these exact encoder options:

```python
if profile.format == "jpeg":
    image.save(handle, format="JPEG", quality=profile.quality, subsampling=0, optimize=True,
               icc_profile=prepared.icc_bytes, exif=prepared.exif_bytes)
elif profile.format == "png":
    image.save(handle, format="PNG", optimize=True, icc_profile=prepared.icc_bytes, exif=prepared.exif_bytes)
elif profile.format == "webp":
    image.save(handle, format="WEBP", quality=profile.quality, method=6, icc_profile=prepared.icc_bytes,
               exif=prepared.exif_bytes)
```

Flush and `os.fsync()` the file, reopen it with Pillow, and verify format and dimensions. Recheck that the destination does not exist, then use Windows `os.rename(temp_path, destination)`, which fails rather than replacing an existing destination. If any operation fails, delete only the unique temporary file. Keep the no-overwrite race test in the Windows test suite by creating the destination immediately before the rename call through an injected pre-rename hook.

- [ ] **Step 6: Run renderer and encoder tests**

Run: `python -m unittest ndex_frame.tests.test_renderer ndex_frame.tests.test_encoders -v`  
Expected: all tests pass and no `*.ndex_tmp` files remain.

- [ ] **Step 7: Commit the export codec boundary**

```powershell
git add ndex_frame/imaging/renderer.py ndex_frame/imaging/encoders.py ndex_frame/tests/test_renderer.py ndex_frame/tests/test_encoders.py
git commit -m "feat(frame): render and encode verified outputs"
```

---

### Task 6: Import analysis and thumbnail/proxy cache

**Files:**
- Create: `ndex_frame/services/importer.py`
- Create: `ndex_frame/services/cache.py`
- Create: `ndex_frame/tests/test_importer.py`
- Create: `ndex_frame/tests/test_cache.py`

**Interfaces:**
- Consumes: Pillow header reads and `SourceItem`.
- Produces: `discover_files(paths, recursive=False) -> list[Path]`, `analyze_source(path) -> SourceItem`, and `PreviewCache(root).get_or_create(source, max_edge) -> Path`.

- [ ] **Step 1: Write deterministic discovery tests**

```python
def test_discover_files_is_case_insensitive_and_sorted(self) -> None:
    self.make_image("B.PNG")
    self.make_image("a.jpg")
    (self.root / "notes.txt").write_text("ignore", encoding="utf-8")
    paths = discover_files([self.root])
    self.assertEqual([path.name for path in paths], ["a.jpg", "B.PNG"])

def test_duplicate_selected_paths_are_returned_once(self) -> None:
    image = self.make_image("same.jpg")
    self.assertEqual(discover_files([image, image]), [image.resolve()])
```

- [ ] **Step 2: Write cache invalidation tests**

```python
def test_cache_reuses_unchanged_source(self) -> None:
    first = self.cache.get_or_create(self.source, 1600)
    second = self.cache.get_or_create(self.source, 1600)
    self.assertEqual(first, second)
    self.assertEqual(first.stat().st_mtime_ns, second.stat().st_mtime_ns)

def test_cache_key_changes_after_source_modification(self) -> None:
    first = self.cache.get_or_create(self.source, 1600)
    self.rewrite_source()
    second = self.cache.get_or_create(self.source, 1600)
    self.assertNotEqual(first, second)
```

- [ ] **Step 3: Run importer/cache tests and verify missing services**

Run: `python -m unittest ndex_frame.tests.test_importer ndex_frame.tests.test_cache -v`  
Expected: import failures.

- [ ] **Step 4: Implement discovery and cheap analysis**

Support suffixes `{.jpg, .jpeg, .png, .tif, .tiff}`. Resolve and deduplicate paths with `os.path.normcase()`. Read image dimensions, EXIF orientation, and ICC presence without decoding a full-resolution pixel buffer. Return warnings rather than dropping a file when ICC is missing.

- [ ] **Step 5: Implement cache keys and proxy generation**

```python
def cache_key(source: Path, max_edge: int) -> str:
    stat = source.stat()
    payload = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{max_edge}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

Generate oriented, sRGB JPEG proxies with longest edge at most `max_edge`, Quality 88, and a unique atomic temporary file. A cache failure must return a service error that allows the caller to fall back to direct preview generation.

- [ ] **Step 6: Run importer/cache tests**

Run: `python -m unittest ndex_frame.tests.test_importer ndex_frame.tests.test_cache -v`  
Expected: all tests pass.

- [ ] **Step 7: Commit import and preview cache**

```powershell
git add ndex_frame/services/importer.py ndex_frame/services/cache.py ndex_frame/tests/test_importer.py ndex_frame/tests/test_cache.py
git commit -m "feat(frame): analyze masters and cache previews"
```

---

### Task 7: Export planning, collision handling, progress, and cancellation

**Files:**
- Create: `ndex_frame/core/validation.py`
- Create: `ndex_frame/services/export_job.py`
- Create: `ndex_frame/tests/test_export_job.py`

**Interfaces:**
- Consumes: `SourceItem`, presets, overrides, `resolve_canvas`, `build_render_plan`, `prepare_master`, `render`, and `save_output_atomic`.
- Produces: `ExportRequest`, `ExportItemPlan`, `ExportJobSnapshot`, `ExportResult`, `CancelToken`, `plan_export(request)`, and `run_export(snapshot, progress, cancel)`.

- [ ] **Step 1: Write collision-planning tests**

```python
def test_existing_file_is_skipped_without_overwrite(self) -> None:
    existing = self.output / "IMG_001.jpg"
    existing.write_bytes(b"keep")
    plan = plan_export(self.request(collision_policy="skip"))
    self.assertEqual(plan.items[0].action, "skip")
    self.assertEqual(existing.read_bytes(), b"keep")

def test_rename_policy_uses_incrementing_suffix(self) -> None:
    (self.output / "IMG_001.jpg").write_bytes(b"one")
    (self.output / "IMG_001_01.jpg").write_bytes(b"two")
    plan = plan_export(self.request(collision_policy="rename"))
    self.assertEqual(plan.items[0].destination.name, "IMG_001_02.jpg")
```

- [ ] **Step 2: Write failure-isolation and cancel tests**

```python
def test_one_failed_source_does_not_stop_remaining_items(self) -> None:
    result = run_export(self.snapshot_with_bad_middle_item(), progress=lambda event: None, cancel=CancelToken())
    self.assertEqual(result.exported, 2)
    self.assertEqual(result.failed, 1)

def test_cancel_keeps_completed_outputs_and_removes_temp_files(self) -> None:
    token = CancelToken()
    result = run_export(self.snapshot_three_items(cancel_after=1, token=token), self.progress, token)
    self.assertEqual(result.exported, 1)
    self.assertTrue(result.cancelled)
    self.assertEqual(list(self.output.glob("*.ndex_tmp")), [])
```

- [ ] **Step 3: Run tests and verify missing export service**

Run: `python -m unittest ndex_frame.tests.test_export_job -v`  
Expected: import failure.

- [ ] **Step 4: Implement immutable job data and preflight validation**

```python
@dataclass(frozen=True, slots=True)
class ExportRequest:
    sources: tuple[SourceItem, ...]
    output_dir: Path
    frame: FramePreset
    output: OutputProfile
    overrides: tuple[ImageOverride, ...]
    collision_policy: Literal["skip", "rename"]


@dataclass(frozen=True, slots=True)
class ExportItemPlan:
    source: SourceItem
    destination: Path
    render_plan: RenderPlan
    action: Literal["export", "skip", "error"]
    message: str = ""
```

`plan_export()` must snapshot all data, validate output writability with a unique probe, compute canvas dimensions once, reserve unique destination names within the in-memory batch plan, and never create final image files.

- [ ] **Step 5: Implement sequential background-safe execution**

`run_export()` loops over immutable items, checks `cancel.is_cancelled()` before each item, emits `ExportProgress(index, total, source, state, message)`, catches exceptions per item, and returns counts plus item-level messages. It may not catch `KeyboardInterrupt` or `SystemExit`.

- [ ] **Step 6: Run export service tests**

Run: `python -m unittest ndex_frame.tests.test_export_job -v`  
Expected: all tests pass; original and pre-existing destination bytes remain unchanged.

- [ ] **Step 7: Commit batch export orchestration**

```powershell
git add ndex_frame/core/validation.py ndex_frame/services/export_job.py ndex_frame/tests/test_export_job.py
git commit -m "feat(frame): add safe cancellable batch export"
```

---

### Task 8: Workspace state and preview-first PySide6 window

**Files:**
- Create: `ndex_frame/ui/__init__.py`
- Create: `ndex_frame/ui/workspace.py`
- Create: `ndex_frame/ui/preview_widget.py`
- Create: `ndex_frame/ui/main_window.py`
- Create: `ndex_frame/main.py`
- Create: `ndex_frame/__main__.py`
- Create: `ndex_frame/tests/test_workspace.py`
- Create: `ndex_frame/tests/test_main_window.py`

**Interfaces:**
- Consumes: importer, cache, preset store, geometry, and export services.
- Produces: `WorkspaceState`, `WorkspaceController`, `PreviewWidget`, `MainWindow`, and `main() -> int`.

- [ ] **Step 1: Write workspace inheritance and Override tests**

```python
def test_selected_image_inherits_frame_until_modified(self) -> None:
    workspace = self.workspace_with_two_images()
    self.assertFalse(workspace.is_modified(self.first_path))
    workspace.set_selected_framing(photo_scale=0.9, x=0.0, y=0.2)
    self.assertTrue(workspace.is_modified(self.first_path))
    self.assertFalse(workspace.is_modified(self.second_path))

def test_apply_to_all_changes_base_and_clears_overrides(self) -> None:
    workspace = self.workspace_with_two_images()
    workspace.set_selected_framing(0.9, 0.0, 0.2)
    workspace.apply_current_framing_to_all()
    self.assertEqual(workspace.working_frame.photo_scale, 0.9)
    self.assertEqual(workspace.overrides, {})
```

- [ ] **Step 2: Write offscreen UI composition tests**

Set `QT_QPA_PLATFORM=offscreen` before importing PySide6. Instantiate `QApplication` once and assert:

```python
window = MainWindow(controller=self.fake_controller)
self.assertEqual(window.windowTitle(), "NDEX Frame")
self.assertIsNotNone(window.thumbnail_view)
self.assertIsNotNone(window.preview_widget)
self.assertIsNotNone(window.frame_panel)
self.assertEqual(window.export_all_button.text(), "Export All")
```

- [ ] **Step 3: Run tests and verify missing UI modules**

Run: `python -m unittest ndex_frame.tests.test_workspace ndex_frame.tests.test_main_window -v`  
Expected: import failures.

- [ ] **Step 4: Implement non-Qt workspace state**

`WorkspaceState` owns ordered `SourceItem` objects, selected path, working Frame Preset, Output Profile, output directory, and a `dict[Path, ImageOverride]`. `effective_framing(path)` returns override values when present and working-frame values otherwise. `reset_override(path)` removes only that source's override.

- [ ] **Step 5: Implement PreviewWidget drag conversion**

`PreviewWidget` paints the proxy into the widget's displayed canvas rectangle using the shared RenderPlan. On mouse release, convert drag displacement into normalized free-space coordinates in `[-1, 1]`, clamp through `build_render_plan()`, and emit:

```python
framingDragged = Signal(float, float)
```

If an axis has no free space, emit `0.0` for that axis.

- [ ] **Step 6: Compose the approved single-window layout**

Use a top toolbar for file/folder and two preset selectors; a horizontal splitter with thumbnail list, PreviewWidget, and Frame controls; and a bottom bar with Output Folder, computed result summary, Export Selected, and Export All. Scale uses a linked `QSlider(10, 100)` and `QSpinBox(10, 100)`. X/Y use bounded `QDoubleSpinBox(-1.0, 1.0)` controls.

- [ ] **Step 7: Implement the Launcher-compatible startup contract**

`ndex_frame.main.build_parser()` accepts `--open` for parity with sibling apps and optional `--source PATH`. `--open` does not change behavior; when `--source` names an existing directory, queue that folder for import after `MainWindow.show()`. An invalid source is shown as a non-fatal UI error and the empty workspace remains usable.

- [ ] **Step 8: Wire background workers without blocking Qt**

Use `QThreadPool` + `QRunnable` for import/cache work and one dedicated worker object moved to `QThread` for each export job. All UI mutation occurs in slots connected with queued signals. The Cancel button calls only `CancelToken.cancel()`.

- [ ] **Step 9: Run workspace/UI tests and manual dev smoke**

Run: `python -m unittest ndex_frame.tests.test_workspace ndex_frame.tests.test_main_window -v`  
Expected: all tests pass.

Run: `python -m ndex_frame`  
Expected: one NDEX Frame window opens; resizing preserves three panels; closing without a job exits cleanly.

- [ ] **Step 10: Commit the preview-first shell**

```powershell
git add ndex_frame/ui ndex_frame/main.py ndex_frame/__main__.py ndex_frame/tests/test_workspace.py ndex_frame/tests/test_main_window.py
git commit -m "feat(frame): add preview-first PySide6 workspace"
```

---

### Task 9: Preset dialogs, export UX, and end-to-end application behavior

**Files:**
- Create: `ndex_frame/ui/profile_dialog.py`
- Create: `ndex_frame/ui/preset_dialog.py`
- Create: `ndex_frame/tests/test_profile_dialog.py`
- Create: `ndex_frame/tests/test_app_flow.py`
- Modify: `ndex_frame/ui/main_window.py`

**Interfaces:**
- Consumes: `PresetStore`, `WorkspaceController`, `plan_export`, and `run_export`.
- Produces: complete file/folder import, Profile editing, default selection, Preview status, preflight conflict selection, progress/cancel, and completion summary.

- [ ] **Step 1: Write Profile dialog validation tests**

```python
def test_profile_dialog_shows_computed_dimensions(self) -> None:
    dialog = OutputProfileDialog(self.instagram_profile, AspectRatio(3, 4))
    self.assertEqual(dialog.computed_size_label.text(), "1080 × 1440")

def test_builtin_profile_save_creates_custom_copy(self) -> None:
    dialog = OutputProfileDialog(self.instagram_profile, AspectRatio(3, 4))
    dialog.name_edit.setText("Instagram Feed HQ Custom")
    saved = dialog.build_profile()
    self.assertTrue(saved.id.startswith("custom."))
    self.assertFalse(saved.builtin)
```

- [ ] **Step 2: Write an end-to-end controller flow test**

Create two small temporary Master images, import the folder, select the second, set Scale 90% and Y 0.5, run preflight with rename policy, execute Export All, and assert two 1080×1440 files exist while only the second source is marked Modified before export.

- [ ] **Step 3: Run dialog/app-flow tests and verify failures**

Run: `python -m unittest ndex_frame.tests.test_profile_dialog ndex_frame.tests.test_app_flow -v`  
Expected: missing dialog and incomplete flow failures.

- [ ] **Step 4: Implement Profile and Frame Preset management**

The Output Profile dialog exposes format and sizing in its basic section. Its Advanced section exposes Quality, chroma, color space, ICC checkbox, and metadata policy. `Set as Default` writes only the selected preset kind. Built-ins show `Duplicate as Custom Preset`; custom presets show `Save`, `Save As`, and `Delete`.

- [ ] **Step 5: Implement preflight and collision dialog**

Before Export, show counts for exportable, skipped, conflicted, and invalid items. When conflicts exist, require the user to select `Skip existing` or `Auto rename`; there is no overwrite option. Disable Export if Output Folder is unavailable or no source is exportable.

- [ ] **Step 6: Implement progress, cancel, and completion UI**

Progress shows current filename and `current / total`. Cancel requests cooperative cancellation and changes the button text to `Cancelling…` until the worker returns. Completion displays exported, skipped, failed, and cancelled counts and offers `Open Output Folder`.

- [ ] **Step 7: Run end-to-end tests and the entire NDEX suite**

Run:

```powershell
python -m unittest discover -s ndex_frame\tests -v
python -m unittest discover -s tests -v
python -m unittest discover -s dsb_image_manager\tests -v
python -m unittest discover -s ndex_auto_selector\tests -v
python -m unittest discover -s ndex_launcher\tests -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit complete application behavior**

```powershell
git add ndex_frame/ui ndex_frame/tests
git commit -m "feat(frame): complete preset and batch export workflow"
```

---

### Task 10: Windows packaging, release assembly, launcher integration, and fresh smoke test

**Files:**
- Create: `ndex_frame/build_package.ps1`
- Create: `ndex_frame/tests/smoke_packaged.ps1`
- Modify: `ndex_frame/main.py`
- Modify: `ndex_common/launch.py`
- Modify: `ndex_launcher/state.py`
- Modify: `ndex_launcher/main.py`
- Modify: `ndex_launcher/tests/test_state.py`
- Modify: `build_all.ps1`
- Modify: `release_README.md`
- Modify: `THIRD_PARTY_NOTICES.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: complete NDEX Frame app and existing PyInstaller/version/launcher infrastructure.
- Produces: `ndex_frame/dist/NDEX_Frame.exe`, a five-app portable release, and a fourth Launcher workflow card.

- [ ] **Step 1: Write launcher-state failure first**

Update the expected keys in `ndex_launcher/tests/test_state.py`:

```python
self.assertEqual(
    [step.key for step in steps],
    ["ndex_one", "image_manager", "auto_selector", "frame"],
)
self.assertEqual(steps[3].launch_args, ["--open"])
```

Run: `python -m unittest ndex_launcher.tests.test_state -v`  
Expected: failure because the Frame step is absent.

- [ ] **Step 2: Add Frame launch resolution and workflow state**

Add:

```python
"frame": ("NDEX_Frame.exe", "ndex_frame.main"),
```

to `APP_COMMANDS`, add `ndex_frame/dist` to `_DIST_SUBDIRS`, and append a `StepState` with title `4. Frame & Export - NDEX Frame`. Read `frame.last_source` from shared settings and pass `--open --source <folder>` only when that folder exists.

- [ ] **Step 3: Make Launcher cards responsive for four steps**

Replace hard-coded columns `(0, 2, 4)` with a loop over the returned step count. At widths below 1100px, use a 2×2 card grid without arrow columns; at larger widths, use one four-card row. Add an offscreen or state-level test that all four cards are created.

- [ ] **Step 4: Add the hidden packaged-smoke entry point**

Extend `ndex_frame.main.build_parser()` with:

```python
parser.add_argument(
    "--smoke-export",
    nargs=2,
    type=Path,
    metavar=("SOURCE", "OUTPUT_DIR"),
    help=argparse.SUPPRESS,
)
```

When present, `main()` must not create a `QApplication`. It loads the two built-in defaults through `PresetStore`, analyzes the one source, builds a one-item snapshot with collision policy `rename`, executes the normal export service, prints one JSON result line, and exits `0` only when exactly one output was exported. Add a unit test that patches `run_export()` and proves the Qt startup function is not called.

- [ ] **Step 5: Write the NDEX Frame PyInstaller script**

Follow the existing sibling build scripts and include:

```powershell
python -m PyInstaller `
  --noconfirm --clean --onefile --windowed `
  --name NDEX_Frame `
  --paths $appRoot --paths $repoRoot `
  --collect-submodules ndex_frame `
  --collect-submodules ndex_common `
  --collect-all PySide6 `
  --hidden-import PIL.ImageCms `
  --add-data "$repoRoot\assets\branding;assets\branding" `
  --add-data "$appRoot\resources;ndex_frame\resources" `
  --icon "$repoRoot\assets\branding\ndex_icon.ico" `
  $entryPoint
```

Generate the version resource with product `NDEX Frame`, executable `NDEX_Frame`, and description `NDEX Frame - photography framing and export`.

- [ ] **Step 6: Update the five-app release builder**

Change progress labels from `[1/4]` through `[4/4]` to `[1/5]` through `[5/5]`, invoke `ndex_frame/build_package.ps1` before Launcher, and add:

```powershell
@{ Source = "ndex_frame\dist\NDEX_Frame.exe"; Target = "NDEX_Frame.exe" }
```

to release artifacts.

- [ ] **Step 7: Add third-party notices and ignore rules**

Record the exact PySide6, Qt, shiboken6, and Pillow versions resolved by the build environment and include their license texts or authoritative license references in `THIRD_PARTY_NOTICES.md`. Add these ignore rules:

```gitignore
.superpowers/
ndex_frame/build/
ndex_frame/dist/
```

- [ ] **Step 8: Build and run packaged smoke tests**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\ndex_frame\build_package.ps1
powershell -ExecutionPolicy Bypass -File .\ndex_frame\tests\smoke_packaged.ps1
```

The smoke script must create a temporary 1200×1800 sRGB JPEG containing copyright and GPS EXIF, hash the source, launch `NDEX_Frame.exe --smoke-export <source> <output-dir>`, parse the JSON result, then assert output is 1080×1440, JPEG, contains ICC, has no GPS, retains copyright, and leaves the source hash unchanged.

- [ ] **Step 9: Run full fresh verification**

Run:

```powershell
python -m unittest discover -s ndex_frame\tests -v
python -m unittest discover -s tests -v
python -m unittest discover -s dsb_image_manager\tests -v
python -m unittest discover -s ndex_auto_selector\tests -v
python -m unittest discover -s ndex_launcher\tests -v
powershell -ExecutionPolicy Bypass -File .\build_all.ps1
```

Start the packaged app from the assembled release, import a mixed portrait/landscape folder, verify Preview against three exported files, cancel a second batch, and confirm no Master or existing output changed.

- [ ] **Step 10: Commit release integration**

```powershell
git add ndex_frame/main.py ndex_frame/build_package.ps1 ndex_frame/tests/smoke_packaged.ps1 ndex_common/launch.py ndex_launcher build_all.ps1 release_README.md THIRD_PARTY_NOTICES.md .gitignore
git commit -m "build(frame): package and integrate NDEX Frame"
```

---

## Final Acceptance Checklist

- [ ] `White 3:4 + Instagram Feed HQ` opens as the independent default pair.
- [ ] A 3:4 portrait fills 1080×1440 without a border; a 5:7 portrait receives side borders; landscape receives top/bottom borders.
- [ ] Scale 100% never crops, and drag cannot move pixels outside the canvas.
- [ ] Preview and Export edges agree within one output pixel.
- [ ] sRGB and non-sRGB tagged Masters export as tagged sRGB; untagged Masters show a warning.
- [ ] JPEG output is Quality 95 and 4:4:4; GPS is absent and copyright remains.
- [ ] Individual edits create `Modified` state; Reset and Apply to All behave as designed.
- [ ] Existing output is skipped or renamed and never overwritten.
- [ ] Batch error and cancellation leave no temporary files and do not modify Masters.
- [ ] All NDEX unit tests and the packaged smoke test pass from fresh commands.
- [ ] The portable release contains all five executables and Launcher opens NDEX Frame.

