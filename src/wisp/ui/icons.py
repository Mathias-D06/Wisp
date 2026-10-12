"""Programmatic icons: the Wisp orb in each assistant state."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QRadialGradient

STATE_COLORS = {
    "idle": None,  # accent
    "listening": "#4ade80",
    "thinking": "#facc15",
    "speaking": None,  # accent, brighter
    "offline": "#6b7280",
    "error": "#f87171",
}


def orb_pixmap(size: int, accent: str, state: str = "idle") -> QPixmap:
    color = QColor(STATE_COLORS.get(state) or accent)
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    center = QPointF(size / 2, size / 2)
    gradient = QRadialGradient(QPointF(size * 0.38, size * 0.35), size * 0.62)
    gradient.setColorAt(0.0, color.lighter(170))
    gradient.setColorAt(0.55, color)
    gradient.setColorAt(1.0, color.darker(160))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    radius = size * 0.42
    painter.drawEllipse(center, radius, radius)
    painter.end()
    return pix


def orb_icon(accent: str, state: str = "idle") -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 256):
        icon.addPixmap(orb_pixmap(size, accent, state))
    return icon
