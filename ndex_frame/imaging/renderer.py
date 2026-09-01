from __future__ import annotations

from PIL import Image

from ndex_frame.core.models import RenderPlan
from ndex_frame.imaging.color import PreparedImage


def render(prepared: PreparedImage, plan: RenderPlan, background: str) -> Image.Image:
    """Render one prepared master image into its integer export canvas."""
    canvas = Image.new("RGB", (plan.canvas_width, plan.canvas_height), background)
    resized = prepared.image.resize((plan.photo_width, plan.photo_height), Image.Resampling.LANCZOS)
    canvas.paste(resized, (plan.left, plan.top))
    return canvas
