"""Preview canvas that projects the immutable export RenderPlan."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ndex_frame.core.geometry import ProjectedRenderPlan, build_render_plan, project_render_plan
from ndex_frame.core.models import RenderPlan


class PreviewWidget(QWidget):
    framingDragged = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 360)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._pixmap = QPixmap()
        self._plan: RenderPlan | None = None
        self._background = "#FFFFFF"
        self._x = 0.0
        self._y = 0.0
        self._drag_start: QPoint | None = None

    def set_preview(
        self,
        pixmap: QPixmap,
        plan: RenderPlan,
        background: str = "#FFFFFF",
        x: float = 0.0,
        y: float = 0.0,
    ) -> None:
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
        painter.fillRect(self.rect(), QColor("#202124"))
        projected = self.projected_plan()
        if projected is None:
            painter.setPen(QColor("#AEB4BD"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Open files or a folder to preview")
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
        self.framingDragged.emit(x, y)
