"""Small status pill near the bottom of the screen (dictation, Circle to Ask, notices).

It never takes focus or mouse input, so the window being dictated into keeps the caret.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget


class Hud(QWidget):
    def __init__(self, accent: str = "#7c5cff"):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.accent = accent
        self.text = ""
        self.dot = accent
        self._level: Callable[[], float] | None = None
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self.update)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self.setFixedSize(280, 44)

    def show_state(self, text: str, dot: str | None = None,
                   level: Callable[[], float] | None = None) -> None:
        self._hide_timer.stop()
        self.text = text
        self.dot = dot or self.accent
        self._level = level
        self._place()
        self.show()
        self._ticker.start(50)
        self.update()

    def flash(self, text: str, ms: int = 2500, dot: str | None = None) -> None:
        self.show_state(text, dot)
        self._hide_timer.start(ms)

    def hide_now(self) -> None:
        self._ticker.stop()
        self.hide()

    def _place(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.x() + (area.width() - self.width()) // 2,
                  area.y() + area.height() - self.height() - 72)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.fillPath(path, QColor(20, 20, 26, 235))
        painter.setPen(QColor(255, 255, 255, 40))
        painter.drawPath(path)
        level = min(1.0, (self._level() if self._level else 0.0) * 1.6)
        radius = 5 + 4 * level
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.dot))
        painter.drawEllipse(QRectF(22 - radius, rect.center().y() - radius, radius * 2,
                                   radius * 2))
        painter.setPen(QColor("#f2f2f7"))
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        painter.drawText(rect.adjusted(38, 0, -14, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(self.text, Qt.TextElideMode.ElideRight,
                                                          int(rect.width()) - 52))
        painter.end()
