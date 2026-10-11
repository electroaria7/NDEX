"""Virtualized thumbnail grid: only the tiles near the viewport exist on the canvas."""
from __future__ import annotations

import tkinter as tk
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

from PIL import ImageTk

from ndex_common.theme import (
    ACCENT,
    BORDER,
    CARD_BG,
    PREVIEW_WELL,
    PREVIEW_WELL_TEXT,
    SELECTION_BG,
    STAR,
    SURFACE_SUNKEN,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

from ..services.thumbnails import ThumbnailLoader
from . import grid_model as gm

STAR_FILLED = "★"
PICK_COLORS = {"Pick": "#15803d", "Maybe": "#b45309", "Reject": "#b91c1c"}
CACHE_LIMIT = 320


@dataclass
class TileInfo:
    iid: str
    title: str
    kind: str
    pick: str
    glyph: str
    rating: int
    thumb: Path | None
    fallback: Callable[[], Path | None] | None = None


class ThumbnailGrid(tk.Frame):
    """A scrolling canvas of tiles. The owner supplies rows and per-row tile data."""

    def __init__(
        self,
        parent,
        *,
        rows: Callable[[], list],
        describe: Callable[[object], TileInfo],
        selected: Callable[[], "set[str] | frozenset[str]"],
        focused: Callable[[], str],
        on_click: Callable[[int, bool, bool], None],
        on_activate: Callable[[int], None],
        tile_px: int = 160,
        scale: float = 1.0,
        loader: ThumbnailLoader | None = None,
    ):
        super().__init__(parent, bg=SURFACE_SUNKEN, bd=0, highlightthickness=0)
        self._rows, self._describe, self._selected, self._focused = rows, describe, selected, focused
        self._on_click, self._on_activate = on_click, on_activate
        self._scale = scale
        self.loader = loader or ThumbnailLoader()
        self._owns_loader = loader is None
        self._cache: OrderedDict[tuple[str, int], ImageTk.PhotoImage] = OrderedDict()
        self._failed: set[tuple[str, int]] = set()
        self._tiles: dict[int, tuple] = {}
        self._job: str | None = None
        self._poll_job: str | None = None
        self._layout_key: tuple | None = None
        self._cols = 1
        self._offset = 0
        self._n = 0
        self.draw_count = 0

        base = tkfont.nametofont("TkDefaultFont")
        self._title_font = tkfont.Font(self, font=base)
        self._small_font = tkfont.Font(self, font=base)
        self._small_font.configure(size=max(7, abs(base.cget("size")) - 1))
        self._badge_font = tkfont.Font(self, font=base)
        self._badge_font.configure(weight="bold")
        self.canvas = tk.Canvas(self, bg=SURFACE_SUNKEN, bd=0, highlightthickness=0, takefocus=True)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", self._double)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.metrics = self._make_metrics(tile_px)

    # ---- geometry ----

    def _make_metrics(self, tile_px: int) -> gm.GridMetrics:
        line = self._title_font.metrics("linespace")
        small = self._small_font.metrics("linespace")
        s = self._scale
        caption = line + small + int(10 * s)
        return gm.GridMetrics(tile=int(tile_px), caption=caption, gap=int(10 * s), pad=int(12 * s))

    def set_tile_size(self, tile_px: int) -> None:
        anchor = self.top_index()
        self.metrics = self._make_metrics(tile_px)
        self._cache.clear()
        self._failed.clear()
        self._tiles.clear()
        self.canvas.delete("all")
        self._layout_key = None
        self._relayout()
        self.scroll_to_index(anchor)
        self.invalidate()

    @property
    def columns(self) -> int:
        return self._cols

    def _view_size(self) -> tuple[int, int]:
        return max(self.canvas.winfo_width(), 1), max(self.canvas.winfo_height(), 1)

    def _relayout(self) -> None:
        """Column count and scroll region; keeps the first visible tile in place when columns change."""
        width, _height = self._view_size()
        n = len(self._rows())
        cols = gm.columns(width, self.metrics)
        key = (n, cols, width, self.metrics.tile)
        if key == self._layout_key:
            return
        anchor = gm.top_index(int(self.canvas.canvasy(0)), self._cols, self.metrics) if self._layout_key else 0
        cols_changed = cols != self._cols
        self._layout_key = key
        self._cols, self._n = cols, n
        self._offset = gm.left_offset(width, cols, self.metrics)
        height = gm.content_height(n, cols, self.metrics)
        self.canvas.configure(scrollregion=(0, 0, width, max(height, 1)), yscrollincrement=max(16, self.metrics.cell_h // 6))
        if cols_changed:
            self._tiles.clear()
            self.canvas.delete("all")
            self._set_scroll(gm.scroll_for_index(anchor, cols, self.metrics))

    def _set_scroll(self, y: int) -> None:
        total = gm.content_height(self._n, self._cols, self.metrics)
        max_scroll = max(0, total - self._view_size()[1])
        y = max(0, min(int(y), max_scroll))
        self.canvas.yview_moveto(y / total if total else 0)

    def scroll_y(self) -> int:
        return int(self.canvas.canvasy(0))

    def top_index(self) -> int:
        return gm.top_index(self.scroll_y(), self._cols, self.metrics)

    def scroll_to_index(self, index: int) -> None:
        self._relayout()
        self._set_scroll(gm.scroll_for_index(max(0, index), self._cols, self.metrics))
        self.invalidate()

    def reveal(self, index: int) -> None:
        self._relayout()
        target = gm.scroll_to_reveal(index, self.scroll_y(), self._view_size()[1], self._n, self._cols, self.metrics)
        if target != self.scroll_y():
            self._set_scroll(target)
        self.invalidate()

    # ---- events ----

    def _on_configure(self, _event=None) -> None:
        self.invalidate()

    def _on_yscroll(self, first, last) -> None:
        self.scrollbar.set(first, last)
        self.invalidate()

    def _wheel(self, event) -> str:
        self.canvas.yview_scroll(int(-event.delta / 120 * 3), "units")
        return "break"

    def _hit(self, event) -> int | None:
        self._relayout()
        x, y = int(self.canvas.canvasx(event.x)), int(self.canvas.canvasy(event.y))
        return gm.index_at(x, y, self._n, self._cols, self.metrics, self._offset)

    def _click(self, event) -> None:
        self.canvas.focus_set()
        index = self._hit(event)
        if index is not None:
            self._on_click(index, bool(event.state & 0x1), bool(event.state & 0x4))

    def _double(self, event) -> None:
        index = self._hit(event)
        if index is not None:
            self._on_activate(index)

    # ---- drawing ----

    def invalidate(self) -> None:
        if self._job is None:
            self._job = self.after_idle(self._draw)

    def _truncate(self, text: str, width: int) -> str:
        font = self._title_font
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def _draw(self) -> None:
        self._job = None
        if not self.winfo_exists():
            return
        self.draw_count += 1
        self._relayout()
        rows = self._rows()
        n = len(rows)
        m = self.metrics
        first, stop = gm.visible_range(self.scroll_y(), self._view_size()[1], n, self._cols, m)
        for index in [i for i in self._tiles if not first <= i < stop]:
            self.canvas.delete(f"t{index}")
            del self._tiles[index]
        selected, focused = self._selected(), self._focused()
        needed: list[tuple[tuple[str, int], Callable | None]] = []
        for index in range(first, stop):
            info = self._describe(rows[index])
            key = (str(info.thumb or ""), m.tile)
            image = self._cache.get(key)
            if image is not None:
                self._cache.move_to_end(key)
            known = image is not None or key in self._failed
            sig = (info.iid, info.title, info.kind, info.pick, info.rating, info.iid in selected,
                   info.iid == focused, known, self._offset, self._cols, m.tile)
            if self._tiles.get(index) == sig:
                if not known:
                    needed.append((key, info.fallback))
                continue
            self.canvas.delete(f"t{index}")
            self._tiles[index] = sig
            self._draw_tile(index, info, image, info.iid in selected, info.iid == focused)
            if not known:
                needed.append((key, info.fallback))
        self.loader.want(key for key, _fallback in needed)
        for key, fallback in needed:
            self.loader.request(key, fallback)
        if (needed or self.loader.pending()) and self._poll_job is None:
            self._poll_job = self.after(25, self._poll)

    def _poll(self) -> None:
        self._poll_job = None
        if not self.winfo_exists():
            return
        changed = False
        for key, pil in self.loader.drain(8):
            if pil is None:
                self._failed.add(key)
            elif key not in self._cache:
                self._cache[key] = ImageTk.PhotoImage(pil)
                while len(self._cache) > CACHE_LIMIT:
                    self._cache.popitem(last=False)
            changed = True
        if changed:
            self.invalidate()
        if self.loader.pending() or self.loader.has_results():
            self._poll_job = self.after(25, self._poll)

    def _draw_tile(self, index: int, info: TileInfo, image, selected: bool, focused: bool) -> None:
        c, m, tag = self.canvas, self.metrics, f"t{index}"
        x0, y0 = gm.tile_origin(index, self._cols, m, self._offset)
        x1, y1 = x0 + m.tile, y0 + m.tile + m.caption
        c.create_rectangle(x0, y0, x1, y1, fill=SELECTION_BG if selected else CARD_BG,
                           outline=ACCENT if selected else BORDER, width=3 if selected else 1, tags=tag)
        inset = 3 if selected else 1
        c.create_rectangle(x0 + inset, y0 + inset, x1 - inset, y0 + m.tile, fill=PREVIEW_WELL, width=0, tags=tag)
        centre = (x0 + m.tile // 2, y0 + (m.tile) // 2)
        if image is not None:
            c.create_image(*centre, image=image, tags=tag)
        else:
            c.create_text(*centre, text="…", fill=PREVIEW_WELL_TEXT, font=self._title_font, tags=tag)
        s = self._scale
        if info.pick in PICK_COLORS:
            size = int(24 * s)
            bx, by = x0 + int(6 * s), y0 + int(6 * s)
            c.create_rectangle(bx, by, bx + size, by + size, fill=PICK_COLORS[info.pick], outline="#ffffff", width=1, tags=tag)
            c.create_text(bx + size // 2, by + size // 2, text=info.glyph, fill="#ffffff", font=self._badge_font, tags=tag)
        if selected:
            size = int(18 * s)
            bx, by = x1 - int(6 * s) - size, y0 + int(6 * s)
            c.create_rectangle(bx, by, bx + size, by + size, fill=ACCENT, outline="#ffffff", width=1, tags=tag)
            c.create_text(bx + size // 2, by + size // 2, text="●", fill="#ffffff", font=self._small_font, tags=tag)
        pad = int(6 * s)
        cap_y = y0 + m.tile + int(3 * s)
        c.create_text(x0 + pad, cap_y, text=self._truncate(info.title, m.tile - 2 * pad), anchor=tk.NW,
                      fill=TEXT_PRIMARY, font=self._title_font, tags=tag)
        line2 = cap_y + self._title_font.metrics("linespace")
        if info.rating > 0:
            c.create_text(x0 + pad, line2, text=STAR_FILLED * info.rating, anchor=tk.NW, fill=STAR,
                          font=self._small_font, tags=tag)
        c.create_text(x1 - pad, line2, text=info.kind, anchor=tk.NE, fill=TEXT_MUTED, font=self._small_font, tags=tag)
        if focused:
            c.create_rectangle(x0 + 4, y0 + 4, x1 - 4, y1 - 4, outline="#ffffff" if image is not None else TEXT_MUTED,
                               dash=(3, 3), tags=tag)

    def destroy(self) -> None:
        for job in (self._job, self._poll_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        if self._owns_loader:
            self.loader.close()
        super().destroy()
