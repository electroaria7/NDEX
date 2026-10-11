"""Pure layout and navigation maths for the thumbnail grid (no Tk, so it is unit-testable)."""
from __future__ import annotations

from dataclasses import dataclass

# Tile edge in unscaled pixels per View > Thumbnail Size choice.
TILE_SIZES = {"small": 110, "medium": 160, "large": 220}
DEFAULT_TILE_SIZE = "medium"


@dataclass(frozen=True)
class GridMetrics:
    """Sizes in pixels. A cell is one tile plus its caption and the gap after it."""

    tile: int
    caption: int
    gap: int
    pad: int

    @property
    def cell_w(self) -> int:
        return self.tile + self.gap

    @property
    def cell_h(self) -> int:
        return self.tile + self.caption + self.gap


def columns(width: int, m: GridMetrics) -> int:
    return max(1, (width - 2 * m.pad + m.gap) // m.cell_w)


def row_count(n: int, cols: int) -> int:
    return 0 if n <= 0 else -(-n // max(cols, 1))


def left_offset(width: int, cols: int, m: GridMetrics) -> int:
    """Centre the block of columns; never less than the padding."""
    return max(m.pad, (width - (cols * m.cell_w - m.gap)) // 2)


def content_height(n: int, cols: int, m: GridMetrics) -> int:
    rows = row_count(n, cols)
    return 0 if rows == 0 else rows * m.cell_h - m.gap + 2 * m.pad


def tile_origin(index: int, cols: int, m: GridMetrics, offset: int) -> tuple[int, int]:
    row, col = divmod(index, cols)
    return offset + col * m.cell_w, m.pad + row * m.cell_h


def visible_range(scroll_y: int, view_h: int, n: int, cols: int, m: GridMetrics, margin_rows: int = 1) -> tuple[int, int]:
    """Half-open range of tile indices whose rows touch the viewport plus a margin."""
    if n <= 0 or view_h <= 0:
        return 0, 0
    rows = row_count(n, cols)
    first_row = max(0, (scroll_y - m.pad) // m.cell_h - margin_rows)
    last_row = min(rows - 1, (scroll_y + view_h - m.pad) // m.cell_h + margin_rows)
    if last_row < first_row:
        return 0, 0
    return first_row * cols, min(n, (last_row + 1) * cols)


def index_at(x: int, y: int, n: int, cols: int, m: GridMetrics, offset: int) -> int | None:
    """Tile under a canvas point, or None for gaps, padding and empty cells."""
    x -= offset
    y -= m.pad
    if x < 0 or y < 0:
        return None
    col, in_x = divmod(x, m.cell_w)
    row, in_y = divmod(y, m.cell_h)
    if col >= cols or in_x >= m.tile or in_y >= m.tile + m.caption:
        return None
    index = row * cols + col
    return index if index < n else None


def move_index(index: int, key: str, cols: int, n: int) -> int:
    """Next tile for an arrow key. Down from a short last row lands on the last tile."""
    if n <= 0:
        return 0
    index = max(0, min(index, n - 1))
    if key == "Left":
        return max(0, index - 1)
    if key == "Right":
        return min(n - 1, index + 1)
    if key == "Up":
        return index - cols if index - cols >= 0 else index
    if key == "Down":
        if index + cols < n:
            return index + cols
        return n - 1 if index // cols < (n - 1) // cols else index
    return index


def arrow_key(offset: int, vertical: bool) -> str:
    if vertical:
        return "Down" if offset > 0 else "Up"
    return "Right" if offset > 0 else "Left"


def scroll_to_reveal(index: int, scroll_y: int, view_h: int, n: int, cols: int, m: GridMetrics) -> int:
    """Smallest scroll change that brings the whole tile (with caption) into view."""
    top = tile_origin(index, cols, m, 0)[1]
    bottom = top + m.tile + m.caption
    max_scroll = max(0, content_height(n, cols, m) - view_h)
    if top - m.pad < scroll_y:
        scroll_y = top - m.pad
    elif bottom + m.pad > scroll_y + view_h:
        scroll_y = bottom + m.pad - view_h
    return max(0, min(scroll_y, max_scroll))


def top_index(scroll_y: int, cols: int, m: GridMetrics) -> int:
    """First tile of the row at the top edge of the viewport."""
    return max(0, (scroll_y - m.pad) // m.cell_h) * cols


def scroll_for_index(index: int, cols: int, m: GridMetrics) -> int:
    return max(0, tile_origin(index, cols, m, 0)[1] - m.pad)


def range_between(order: list[str], anchor: str, target: str) -> list[str]:
    """Ids from anchor to target inclusive, in list order (either direction)."""
    try:
        a, b = order.index(anchor), order.index(target)
    except ValueError:
        return [target] if target in order else []
    lo, hi = min(a, b), max(a, b)
    return order[lo : hi + 1]
