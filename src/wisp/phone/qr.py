"""A QR code for the phone link (segno; quiet zone of four modules, error correction M)."""

from __future__ import annotations

import segno
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter


def modules(text: str) -> list[list[int]]:
    """Rows of 1 (dark) and 0 (light), quiet zone included."""
    code = segno.make(text, error="m", micro=False)
    return [list(row) for row in code.matrix_iter(scale=1, border=4)]


def image(text: str, size: int) -> QImage:
    """The code drawn black on white (what phone cameras read best) at ``size`` px."""
    rows = modules(text)
    count = len(rows)
    picture = QImage(size, size, QImage.Format.Format_RGB32)
    picture.fill(QColor(Qt.GlobalColor.white))
    module = size / count
    painter = QPainter(picture)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(Qt.GlobalColor.black))
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            if value:
                painter.drawRect(QRectF(x * module, y * module, module + 0.5, module + 0.5))
    painter.end()
    return picture
