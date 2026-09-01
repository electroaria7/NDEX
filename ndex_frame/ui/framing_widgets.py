"""Shared Frame-panel preset button rows."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from ndex_frame.core.framing_choices import BACKGROUND_PRESETS, PHOTO_SIZE_PRESETS, RATIO_PRESETS
from ndex_frame.core.models import AspectRatio

_SWATCH_SIZE = 30
_SWATCH_RADIUS = 6.0


class ColorSwatchButton(QPushButton):
    """Color chip that paints its own rounded rect so borders are never clipped."""

    def __init__(self, name: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fill = QColor(color)
        outline = "#C3CDDB" if color.upper() in {"#FFFFFF", "#D0D0D0"} else "#1B2433"
        self._outline = QColor(outline)
        self.setObjectName("colorSwatch")
        self.setFixedSize(_SWATCH_SIZE, _SWATCH_SIZE)
        self.setToolTip(name)
        self.setAccessibleName(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Inset by 1px so the stroke stays inside the widget bounds.
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        path = QPainterPath()
        path.addRoundedRect(rect, _SWATCH_RADIUS, _SWATCH_RADIUS)
        painter.fillPath(path, self._fill)
        pen = QPen(self._outline)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)
        if self.hasFocus():
            focus = QPen(QColor("#2563EB"))
            focus.setWidthF(1.5)
            painter.setPen(focus)
            painter.drawPath(path)


def make_named_preset_buttons(
    labels: tuple[str, ...],
    on_click: Callable[[str], None],
) -> tuple[QWidget, list[QPushButton]]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    buttons: list[QPushButton] = []
    for label in labels:
        button = QPushButton(label)
        button.setObjectName("compactButton")
        button.clicked.connect(lambda _checked=False, value=label: on_click(value))
        layout.addWidget(button)
        buttons.append(button)
    layout.addStretch(1)
    return row, buttons


def make_background_swatches(
    on_click: Callable[[str], None],
    on_custom: Callable[[], None] | None = None,
) -> tuple[QWidget, list[QPushButton], QPushButton]:
    row = QWidget()
    row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(8)
    buttons: list[QPushButton] = []
    for name, color in BACKGROUND_PRESETS:
        button = ColorSwatchButton(name, color)
        button.clicked.connect(lambda _checked=False, value=color: on_click(value))
        layout.addWidget(button)
        buttons.append(button)
    custom = QPushButton("Custom…")
    custom.setObjectName("compactButton")
    custom.setAccessibleName("Custom background")
    custom.setFixedHeight(_SWATCH_SIZE)
    custom.setMinimumWidth(72)
    if on_custom is not None:
        custom.clicked.connect(lambda _checked=False: on_custom())
    layout.addWidget(custom)
    layout.addStretch(1)
    return row, buttons, custom


def make_background_preset_buttons(
    on_click: Callable[[str], None],
    on_custom: Callable[[], None] | None = None,
) -> tuple[QWidget, list[QPushButton], QPushButton]:
    return make_background_swatches(on_click, on_custom)


def make_ratio_preset_buttons(on_click: Callable[[AspectRatio], None]) -> tuple[QWidget, list[QPushButton]]:
    labels = tuple(label for label, _width, _height in RATIO_PRESETS)
    ratios = {label: AspectRatio(width, height) for label, width, height in RATIO_PRESETS}

    def _clicked(label: str) -> None:
        on_click(ratios[label])

    return make_named_preset_buttons(labels, _clicked)


def make_photo_size_preset_buttons(on_click: Callable[[int], None]) -> tuple[QWidget, list[QPushButton]]:
    labels = tuple(f"{value}%" for value in PHOTO_SIZE_PRESETS)
    sizes = dict(zip(labels, PHOTO_SIZE_PRESETS, strict=True))

    def _clicked(label: str) -> None:
        on_click(sizes[label])

    return make_named_preset_buttons(labels, _clicked)
