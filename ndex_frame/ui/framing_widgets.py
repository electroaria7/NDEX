"""Shared Frame-panel preset button rows."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ndex_frame.core.framing_choices import BACKGROUND_PRESETS, PHOTO_SIZE_PRESETS


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


def make_background_preset_buttons(on_click: Callable[[str], None]) -> tuple[QWidget, list[QPushButton]]:
    names = tuple(name for name, _color in BACKGROUND_PRESETS)
    colors = dict(BACKGROUND_PRESETS)

    def _clicked(name: str) -> None:
        on_click(colors[name])

    return make_named_preset_buttons(names, _clicked)


def make_photo_size_preset_buttons(on_click: Callable[[int], None]) -> tuple[QWidget, list[QPushButton]]:
    labels = tuple(f"{value}%" for value in PHOTO_SIZE_PRESETS)
    sizes = dict(zip(labels, PHOTO_SIZE_PRESETS, strict=True))

    def _clicked(label: str) -> None:
        on_click(sizes[label])

    return make_named_preset_buttons(labels, _clicked)
