"""Preview canvas that projects the immutable export RenderPlan."""

from __future__ import annotations

from math import gcd

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ndex_common.i18n import _
from ndex_common.theme import PREVIEW_WELL, PREVIEW_WELL_TEXT
from ndex_frame.core.geometry import ProjectedRenderPlan, build_render_plan, project_render_plan
from ndex_frame.core.models import RenderPlan


HAIRLINE = "#6B7482"


def caption_text(plan: RenderPlan, ratio: tuple[int, int] | None = None) -> str:
    """'1080×1440 · 3:4' for the canvas being previewed."""
    if ratio is None:
        divisor = gcd(plan.canvas_width, plan.canvas_height) or 1
        ratio = (plan.canvas_width // divisor, plan.canvas_height // divisor)
    return f"{plan.canvas_width}×{plan.canvas_height} · {ratio[0]}:{ratio[1]}"


class PreviewWidget(QWidget):
    framingDragged = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 360)
        self.setObjectName("previewWell")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._pixmap = QPixmap()
        self._plan: RenderPlan | None = None
        self._background = "#FFFFFF"
        self._x = 0.0
        self._y = 0.0
        self._drag_start: QPoint | None = None
        self._ratio: tuple[int, int] | None = None
        # Shown until the user has dragged once; then they know.
        self._show_hint = True
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def set_preview(
        self,
        pixmap: QPixmap,
        plan: RenderPlan,
        background: str = "#FFFFFF",
        x: float = 0.0,
        y: float = 0.0,
        ratio: tuple[int, int] | None = None,
    ) -> None:
        self._ratio = ratio
        self._pixmap = pixmap
        self._plan = plan
        self._background = background
        self._x = x
        self._y = y
        self.update()

    def clear(self) -> None:
        self._pixmap = QPixmap()
        self._plan = None
        self.update()

    def projected_plan(self) -> ProjectedRenderPlan | None:
        if self._plan is None or self.width() <= 0 or self.height() <= 0:
            return None
        return project_render_plan(self._plan, (self.width(), self.height()))

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(PREVIEW_WELL))
        projected = self.projected_plan()
        if projected is None:
            painter.setPen(QColor(PREVIEW_WELL_TEXT))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, _("Open photos or a folder to preview\nYou can also drag them into this window"))
            return
        canvas = QRectF(
            projected.canvas_left,
            projected.canvas_top,
            projected.canvas_right - projected.canvas_left,
            projected.canvas_bottom - projected.canvas_top,
        )
        photo = QRectF(
            projected.photo_left,
            projected.photo_top,
            projected.photo_right - projected.photo_left,
            projected.photo_bottom - projected.photo_top,
        )
        painter.fillRect(canvas, QColor(self._background))
        if not self._pixmap.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(photo, self._pixmap, QRectF(self._pixmap.rect()))
        # A hairline so a white or black frame still reads against the dark well.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QColor(HAIRLINE))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(canvas.adjusted(-0.5, -0.5, 0.5, 0.5))
        self._paint_pill(painter, caption_text(self._plan, self._ratio), bottom=True)
        if self._show_hint:
            self._paint_pill(painter, _("Drag the photo to reposition"), bottom=False)

    def _paint_pill(self, painter: QPainter, text: str, *, bottom: bool) -> None:
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 20
        height = metrics.height() + 8
        left = (self.width() - width) / 2.0
        top = self.height() - height - 8 if bottom else 8
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(28, 33, 40, 215))
        painter.drawRoundedRect(QRectF(left, top, width, height), height / 2.0, height / 2.0)
        painter.setPen(QColor("#E6E9EE"))
        painter.drawText(QRectF(left, top, width, height), Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._plan is not None:
            self._drag_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._finish_drag(event.position().toPoint())
        self._drag_start = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def _finish_drag(self, end: QPoint) -> None:
        if self._drag_start is None or self._plan is None:
            return
        projected = self.projected_plan()
        if projected is None:
            return
        free_x = self._plan.canvas_width - self._plan.photo_width
        free_y = self._plan.canvas_height - self._plan.photo_height
        delta = end - self._drag_start
        x = 0.0 if free_x == 0 else self._x + 2.0 * delta.x() / (projected.scale * free_x)
        y = 0.0 if free_y == 0 else self._y + 2.0 * delta.y() / (projected.scale * free_y)
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        # Exercise the same crop-free boundary logic used for export before emitting.
        build_render_plan(
            (self._plan.photo_width, self._plan.photo_height),
            (self._plan.canvas_width, self._plan.canvas_height),
            1.0,
            x,
            y,
        )
        self._show_hint = False
        self.framingDragged.emit(x, y)
