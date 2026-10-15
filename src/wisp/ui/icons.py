"""The Wisp mark (a glowing orb) for the tray, the exe and the installer.

Small sizes (16–24 px) are drawn flat with a crisp edge and a faint halo so they stay readable
in the tray; from 32 px up the halo grows into a soft glow. The state colours match the orb.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from wisp.ui.orb import paint_orb, state_color

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def orb_pixmap(size: int, accent: str, state: str = "idle", badge: str = "") -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    small = size <= 24
    # Small icons: the core fills more of the square and the halo stays faint.
    paint_orb(painter, size, state_color(state, accent), glow=0.25 if small else 0.6,
              scale=1.45 if small else 1.15)
    if badge:
        # A dot in the corner while Wisp is watching the screen (D-052), ringed so it shows
        # on light and dark taskbars.
        diameter = max(6.0, size * 0.42)
        dot = QRectF(size - diameter - 0.5, size - diameter - 0.5, diameter, diameter)
        painter.setPen(QPen(QColor(0, 0, 0, 200), max(1.0, size / 24)))
        painter.setBrush(QColor(badge))
        painter.drawEllipse(dot)
    painter.end()
    return pix


def orb_icon(accent: str, state: str = "idle", badge: str = "") -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(orb_pixmap(size, accent, state, badge))
    return icon
