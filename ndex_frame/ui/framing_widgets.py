"""Shared Frame-panel preset button rows."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ndex_frame.core.framing_choices import BACKGROUND_PRESETS, PHOTO_SIZE_PRESETS, RATIO_PRESETS
from ndex_frame.core.models import AspectRatio


def make_named_preset_buttons(
    labels: tuple[str, ...],
    on_click: Callable[[str], None],
) -> tuple[QWidget, list[QPushButton]]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    buttons: list[QPushButton] = []
    for label in labels:
        button = QPushButton(label)
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
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    buttons: list[QPushButton] = []
    for name, color in BACKGROUND_PRESETS:
        button = QPushButton()
        button.setFixedSize(28, 28)
        button.setToolTip(name)
        button.setAccessibleName(name)
        outline = "#888888" if color.upper() in {"#FFFFFF", "#D0D0D0"} else "#222222"
        button.setStyleSheet(
            f"background-color: {color}; border: 1px solid {outline}; border-radius: 4px;"
        )
        button.clicked.connect(lambda _checked=False, value=color: on_click(value))
        layout.addWidget(button)
        buttons.append(button)
    custom = QPushButton("Custom…")
    custom.setAccessibleName("Custom background")
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
