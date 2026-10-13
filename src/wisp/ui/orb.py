"""The animated orb: shows the assistant's state and acts as a click-to-talk button."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from wisp.ui.icons import STATE_COLORS

TOOLTIPS = {
    "idle": "Click to talk",
    "listening": "Listening — click to stop",
    "thinking": "Thinking…",
    "speaking": "Speaking — click to interrupt",
    "offline": "Offline",
    "error": "Needs attention",
}


class Orb(QWidget):
    clicked = Signal()

    def __init__(self, size: int = 28, accent: str = "#7c5cff", parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._accent = accent
        self.state = "idle"
        self.level = 0.0
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)
        self.setToolTip(TOOLTIPS["idle"])

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self.update()

    def set_state(self, state: str, level: float = 0.0) -> None:
        if state != self.state:
            self.state = state
            self.setToolTip(TOOLTIPS.get(state, state))
        self.level = level

    def _tick(self) -> None:
        self._phase = (self._phase + 0.12) % (2 * math.pi)
        if self.isVisible():
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """Qt reports a double-click as a second press; one toggle per double-click is enough
        (two would start and immediately stop listening)."""
        event.accept()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        color = QColor(STATE_COLORS.get(self.state) or self._accent)
        base = w * 0.34
        if self.state in ("listening", "speaking"):
            radius = base * (1.0 + 0.28 * min(1.0, self.level * 1.6))
        elif self.state == "idle":
            radius = base * (1.0 + 0.04 * math.sin(self._phase * 0.5))
        else:
            radius = base
        center = QPointF(w / 2, w / 2)
        if self.state in ("listening", "speaking"):
            halo = QColor(color)
            halo.setAlpha(60)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(center, radius * 1.35, radius * 1.35)
        gradient = QRadialGradient(QPointF(w * 0.4, w * 0.36), radius * 1.6)
        gradient.setColorAt(0.0, color.lighter(165))
        gradient.setColorAt(0.6, color)
        gradient.setColorAt(1.0, color.darker(170))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(center, radius, radius)
        if self.state == "thinking":
            pen = QPen(QColor(255, 255, 255, 200), max(1.5, w * 0.06))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            arc = QRectF(center.x() - radius * 1.25, center.y() - radius * 1.25,
                         radius * 2.5, radius * 2.5)
            start = int(-math.degrees(self._phase * 2) * 16)
            painter.drawArc(arc, start, 100 * 16)
        painter.end()
