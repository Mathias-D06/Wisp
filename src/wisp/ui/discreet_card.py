"""Discreet mode's answer card (D-053): a small, low-contrast card under the island.

Answers (Screen Assist, spoken replies as text, Watch comments) appear here instead of in the
open island, and fade out after ``card_seconds`` (12 s by default); the card stays while the
pointer is on it. Its text size and background opacity are settings. Only the background is
translucent: the text is drawn fully opaque so it keeps WCAG AA contrast (theme tokens, tested
over white and black). It never takes keyboard focus, and links in an answer don't open.

"Speak it" reads the answer aloud on request (headphones); "Open" shows it in the island.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wisp.ui import motion, theme

WIDTH = 360
MAX_TEXT_HEIGHT = 220


class DiscreetCard(QWidget):
    speak_requested = Signal(str)
    open_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Wisp")
        self.text = ""
        self.kind = ""
        self.seconds = 12
        self._hovered = False
        frame = QFrame(self)
        frame.setObjectName("DiscreetCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(theme.SPACE["m"], theme.SPACE["s"], theme.SPACE["m"],
                                  theme.SPACE["s"])
        layout.setSpacing(theme.SPACE["xs"])
        self.label = QLabel()
        self.label.setObjectName("DiscreetText")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.label.setOpenExternalLinks(False)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidget(self.label)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll)
        row = QHBoxLayout()
        row.addStretch(1)
        self.speak_button = QPushButton("Speak it")
        self.speak_button.clicked.connect(lambda: self.speak_requested.emit(self.text))
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self._open)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.dismiss)
        for button in (self.speak_button, self.open_button, self.close_button):
            button.setObjectName("DiscreetButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(button)
        layout.addLayout(row)
        self._fade = QTimer(self, singleShot=True)
        self._fade.timeout.connect(self._fade_out)
        self.configure(13, 0.92, 12)

    def configure(self, text_px: int, opacity: float, seconds: int) -> None:
        self.seconds = seconds
        background = theme.rgba(theme.DISCREET_CARD, opacity)
        self.setStyleSheet(
            f"#DiscreetCard {{ background: {background}; border-radius: {theme.RADIUS_PANEL}px; }}"
            f" #DiscreetText {{ color: {theme.DISCREET_CARD_TEXT}; font-size: {text_px}px; "
            f"background: transparent; }}"
            f" QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}"
            f" #DiscreetButton {{ color: {theme.DISCREET_CARD_MUTED}; background: transparent; "
            f"border: none; padding: 2px 6px; font-size: {max(11, text_px - 1)}px; }}"
            f" #DiscreetButton:hover {{ color: {theme.DISCREET_CARD_TEXT}; }}")

    # ----- showing ---------------------------------------------------------------------------
    def show_text(self, text: str, anchor: QPoint, kind: str = "answer", final: bool = True,
                  speakable: bool = True, openable: bool = False) -> None:
        """Show ``text`` (Markdown) with its top-centre at ``anchor`` (global, logical px).
        ``final``: the text is complete, so the fade-out countdown starts."""
        self.text, self.kind = text, kind
        self.label.setText(text)
        self.speak_button.setVisible(speakable)
        self.open_button.setVisible(openable)
        self.label.setFixedWidth(WIDTH - 2 * theme.SPACE["m"] - 4)
        self.label.adjustSize()
        self.scroll.setFixedHeight(min(MAX_TEXT_HEIGHT, self.label.sizeHint().height() + 4))
        self.setFixedWidth(WIDTH)
        self.adjustSize()
        self._place(anchor)
        appearing = not self.isVisible()
        self.setWindowOpacity(1.0)
        self.show()
        if appearing:
            motion.window_fade(self, show=True)
        self._fade.stop()
        if final and not self._hovered:
            self._fade.start(self.seconds * 1000)

    def _place(self, anchor: QPoint) -> None:
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else None
        x = anchor.x() - self.width() // 2
        y = anchor.y()
        if area is not None:
            x = max(area.left() + 8, min(x, area.right() - self.width() - 8))
        self.move(QPoint(x, y))

    def dismiss(self) -> None:
        self._fade.stop()
        self.hide()
        self.text, self.kind = "", ""

    def _fade_out(self) -> None:
        if self._hovered:
            return
        motion.window_fade(self, show=False, finished=self.dismiss)

    def _open(self) -> None:
        self.open_requested.emit()
        self.dismiss()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._fade.stop()
        self.setWindowOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        if self.isVisible():
            self._fade.start(self.seconds * 1000)
        super().leaveEvent(event)
