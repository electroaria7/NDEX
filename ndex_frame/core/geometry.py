from decimal import Decimal, ROUND_HALF_UP

from ndex_frame.core.models import AspectRatio, OutputSizing, RenderPlan


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
