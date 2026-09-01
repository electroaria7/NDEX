# Task 2 Report: Deterministic FIT Geometry and Shared RenderPlan

## Result

Implemented crop-free FIT geometry shared through the immutable `RenderPlan` model. Canvas sizing supports all existing `OutputSizing` modes and uses deterministic `Decimal` half-up rounding. Normalized positions are clamped to `[-1, 1]`, and `photo_scale` is restricted to `0.10..1.00`.

## RED/GREEN evidence

RED command:

```text
python -m unittest ndex_frame.tests.test_geometry -v
```

RED output: test module import failed as expected with `ModuleNotFoundError: No module named 'ndex_frame.core.geometry'`.

GREEN command:

```text
python -m unittest ndex_frame.tests.test_geometry -v
```

GREEN output: `Ran 7 tests ... OK`.

Full existing NDEX suite:

```text
python -m unittest discover -s ndex_frame/tests -v
```

Output: `Ran 13 tests ... OK`.

## Files changed

- `ndex_frame/core/geometry.py`: added `resolve_canvas` and `build_render_plan`.
- `ndex_frame/tests/test_geometry.py`: added fixed sizing, FIT/no-crop, clamping, scale-bound, half-up, and parity matrix tests.

The worktree also contains pre-existing untracked `.ndex_data/`; it was not modified or staged.

## Test matrix evidence

The parity test covers source sizes `(3000, 4000)`, `(5000, 7000)`, `(6000, 4000)`, and `(4000, 4000)` at preview widths `270`, `540`, and `1080`, using normalized position `(0.37, -0.42)`. Photo width, photo height, left, and top, after scaling preview coordinates to output coordinates, differ by at most one pixel for every case.

## Self-review

- `resolve_canvas` consumes `AspectRatio` and `OutputSizing` without changing Task 1 models.
- FIT uses the smaller canvas/source ratio, so no photo edge exceeds the canvas.
- Position clamping prevents crop-producing coordinates.
- Odd free-space centered layouts intentionally place the photo at `free_space // 2`, matching integer centering semantics; non-centered positions use deterministic half-up rounding.
- Input dimensions are rejected when non-positive.
- `git diff --check` completed with no whitespace errors.

## Concerns

No functional concerns remain for Task 2. The odd-free-space center convention is a deliberate compatibility detail required by the specified portrait test; downstream Preview and Export must consume the same `RenderPlan` values.

## Existing repository suite verification

The pre-existing suites were run independently with the exact requested commands; all passed and no Task 2 regression was identified.

```text
python -m unittest discover -s tests -v
Ran 15 tests in 0.091s
OK

python -m unittest discover -s dsb_image_manager\tests -v
Ran 8 tests in 1.382s
OK

python -m unittest discover -s ndex_auto_selector\tests -v
Ran 14 tests in 0.191s
OK

python -m unittest discover -s ndex_launcher\tests -v
Ran 3 tests in 0.004s
OK
```

Existing-suite total: 40 tests passed across four suites.

## Reviewer fix round 1: exact-plan viewport projection

### RED

Added `test_projection_round_trips_all_edges_without_integer_recalculation`, covering all four edges for center, boundaries, and near-boundaries across the four source-size cases. Before implementation, the focused command failed during import because `project_render_plan` was not defined.

### GREEN and final verification

Implemented frozen `ProjectedRenderPlan` and `project_render_plan(plan, viewport_size)`. The projection derives floating-point canvas and photo edges from the single integer export `RenderPlan`, with no intermediate viewport integer rounding.

```text
python -m unittest ndex_frame.tests.test_geometry -v
Ran 8 tests in 0.001s
OK

python -m unittest discover -s tests -v
Ran 15 tests in 0.080s
OK

python -m unittest discover -s dsb_image_manager\tests -v
Ran 8 tests in 1.380s
OK

python -m unittest discover -s ndex_auto_selector\tests -v
Ran 14 tests in 0.180s
OK

python -m unittest discover -s ndex_launcher\tests -v
Ran 3 tests in 0.004s
OK
```

Final verification total: 48 tests passed (8 focused geometry plus 40 existing repository tests). `git diff --check` passed. No code changes were made to `build_render_plan`.

## Reviewer fix round 2: axis-correct letterbox projection tests

### RED

Expanded the projection matrix to include horizontal-letterbox viewport `(271, 360)` and vertical-letterbox viewport `(270, 361)` while retaining all four source sizes and five positions. The intentionally unchanged test offset every edge by `canvas_left`; the focused command then failed for the vertical-letterbox case, demonstrating that the test exposed the axis error.

### GREEN and final verification

Corrected the test to subtract `canvas_left` for horizontal edges (left/right) and `canvas_top` for vertical edges (top/bottom). No production code was changed. Exact final commands and summaries:

```text
python -m unittest ndex_frame.tests.test_geometry -v
Ran 8 tests in 0.001s
OK

python -m unittest discover -s tests -v
Ran 15 tests in 0.079s
OK

python -m unittest discover -s dsb_image_manager\tests -v
Ran 8 tests in 1.383s
OK

python -m unittest discover -s ndex_auto_selector\tests -v
Ran 14 tests in 0.191s
OK

python -m unittest discover -s ndex_launcher\tests -v
Ran 3 tests in 0.004s
OK
```

Round 2 final total: 48 tests passed. The out-of-scope invalid direct `RenderPlan`/zero-division finding was intentionally not addressed.
