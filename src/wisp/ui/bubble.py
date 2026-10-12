"""Answer bubble shown next to a circled region (Circle to Ask)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

MAX_WIDTH = 380


class AnswerBubble(QWidget):
    def __init__(self, surface: str = "#1d1d26", border: str = "#33333f"):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        frame = QFrame(self)
        frame.setObjectName("Bubble")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(MAX_WIDTH)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label)
        self.apply_palette(surface, border)
        self.anchor = QRect()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def apply_palette(self, surface: str, border: str) -> None:
        self.setStyleSheet(f"#Bubble {{ background: {surface}; border: 1px solid {border}; "
                           "border-radius: 12px; }")

    def show_at(self, anchor: QRect, text: str) -> None:
        self.anchor = anchor
        self.set_text(text)
        self._hide_timer.stop()
        self.show()

    def set_text(self, text: str) -> None:
        self.label.setText(text)
        natural = self.label.fontMetrics().horizontalAdvance(text) + 12
        self.label.setFixedWidth(max(160, min(MAX_WIDTH, natural)))
        self.adjustSize()
        self._place()

    def finish(self, seconds: float = 12.0) -> None:
        self._hide_timer.start(int(seconds * 1000))

    def mousePressEvent(self, _event) -> None:
        self.hide()

    def _place(self) -> None:
        screen = QGuiApplication.screenAt(self.anchor.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = self.anchor.right() + 12
        if x + self.width() > area.right():
            x = self.anchor.left() - self.width() - 12
        x = max(area.left() + 8, min(x, area.right() - self.width() - 8))
        y = max(area.top() + 8, min(self.anchor.top(), area.bottom() - self.height() - 8))
        self.move(QPoint(x, y))
