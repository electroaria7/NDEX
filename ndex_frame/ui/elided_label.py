"""Single-line labels that keep the full text available at compact widths."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QLabel, QSizePolicy, QStylePainter, QWidget


class ElidedLabel(QLabel):
    """Elide only the painting, preserving text for accessibility and tooltips."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setToolTip(text)
        self.setAccessibleDescription(text)

    def paintEvent(self, event: object) -> None:
        painter = QStylePainter(self)
        text = self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideMiddle, self.contentsRect().width()
        )
        painter.drawItemText(
            self.contentsRect(),
            int(self.alignment()),
            self.palette(),
            self.isEnabled(),
            text,
            QPalette.ColorRole.WindowText,
        )
