from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass

from ndex_frame.core.models import AspectRatio, OutputSizing, RenderPlan


@dataclass(frozen=True, slots=True)
class ProjectedRenderPlan:
    """Floating-point viewport projection of one integer export RenderPlan."""

    viewport_width: int
    viewport_height: int
    scale: float
    canvas_left: float
    canvas_top: float
    canvas_right: float
    canvas_bottom: float
    photo_left: float
    photo_top: float
    photo_right: float
    photo_bottom: float


def _round(value: float) -> int:
    """Round deterministically using decimal half-up semantics."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def resolve_canvas(sizing: OutputSizing, ratio: AspectRatio) -> tuple[int, int]:
    """Resolve an output canvas from sizing constraints and an aspect ratio."""
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


def build_render_plan(
    source_size: tuple[int, int],
    canvas_size: tuple[int, int],
    photo_scale: float,
    x: float,
    y: float,
) -> RenderPlan:
    """Build a crop-free FIT plan with normalized positioning."""
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
    # Keep the exact center on the lower pixel for odd free space; this makes
    # centered layouts stable and matches integer canvas centering semantics.
    left = free_x // 2 if normalized_x == 0.0 else _round((free_x / 2) * (normalized_x + 1.0))
    top = free_y // 2 if normalized_y == 0.0 else _round((free_y / 2) * (normalized_y + 1.0))
    return RenderPlan(canvas_width, canvas_height, photo_width, photo_height, left, top)


def project_render_plan(plan: RenderPlan, viewport_size: tuple[int, int]) -> ProjectedRenderPlan:
    """Project one output plan into a viewport without re-solving or rounding geometry."""
    viewport_width, viewport_height = viewport_size
    if min(viewport_width, viewport_height) <= 0:
        raise ValueError("Viewport dimensions must be positive.")
    scale = min(viewport_width / plan.canvas_width, viewport_height / plan.canvas_height)
    canvas_left = (viewport_width - plan.canvas_width * scale) / 2.0
    canvas_top = (viewport_height - plan.canvas_height * scale) / 2.0
    canvas_right = canvas_left + plan.canvas_width * scale
    canvas_bottom = canvas_top + plan.canvas_height * scale
    photo_left = canvas_left + plan.left * scale
    photo_top = canvas_top + plan.top * scale
    photo_right = photo_left + plan.photo_width * scale
    photo_bottom = photo_top + plan.photo_height * scale
    return ProjectedRenderPlan(
        viewport_width,
        viewport_height,
        scale,
        canvas_left,
        canvas_top,
        canvas_right,
        canvas_bottom,
        photo_left,
        photo_top,
        photo_right,
        photo_bottom,
    )
