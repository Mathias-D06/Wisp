"""Confirmation card: Yes/No for confirm-tier actions, shown near the top of the screen."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from wisp.tools.base import Origin
from wisp.tools.confirm import ConfirmationManager, PendingAction


class _Bridge(QObject):
    event = Signal(str, object)


class ConfirmCard(QWidget):
    def __init__(self, confirmations: ConfirmationManager):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._confirmations = confirmations
        self._items: list[PendingAction] = []
        self._bridge = _Bridge()
        self._bridge.event.connect(self._on_event)
        confirmations.subscribe(lambda kind, item: self._bridge.event.emit(kind, item))

        frame = QFrame(self)
        frame.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        self.title = QLabel("Wisp needs your OK")
        self.title.setStyleSheet("font-weight: 600;")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.hint = QLabel()
        self.hint.setProperty("muted", True)
        self.hint.setWordWrap(True)
        buttons = QHBoxLayout()
        self.yes = QPushButton("Yes, do it")
        self.yes.setProperty("primary", True)
        self.no = QPushButton("No")
        self.yes.clicked.connect(self._approve)
        self.no.clicked.connect(self._reject)
        buttons.addStretch(1)
        buttons.addWidget(self.no)
        buttons.addWidget(self.yes)
        layout.addWidget(self.title)
        layout.addWidget(self.summary)
        layout.addWidget(self.hint)
        layout.addLayout(buttons)
        self.setFixedWidth(420)
        self._expiry = QTimer(self)
        self._expiry.timeout.connect(self._prune)
        self._expiry.start(1000)

    def apply_palette(self, surface: str, border: str) -> None:
        self.setStyleSheet(
            f"#Card {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}"
        )

    def _on_event(self, kind: str, item: PendingAction) -> None:
        if kind == "created":
            self._items.append(item)
        else:
            self._items = [i for i in self._items if i.id != item.id]
        self._render()

    def _prune(self) -> None:
        live = {i.id for i in self._confirmations.pending()}
        before = len(self._items)
        self._items = [i for i in self._items if i.id in live]
        if len(self._items) != before:
            self._render()

    def _render(self) -> None:
        if not self._items:
            self.hide()
            return
        item = self._items[-1]
        self.summary.setText(item.summary[:300])
        if item.origin == Origin.SCHEDULE:
            self.title.setText("A scheduled task needs your OK")
            self.hint.setText("Click Yes to run this step or No to skip it.")
        else:
            self.title.setText("Wisp needs your OK")
            self.hint.setText("Say “yes” or “no”, or click.")
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + (screen.width() - self.width()) // 2, screen.y() + 64)
        self.show()
        self.raise_()

    def _approve(self) -> None:
        if self._items:
            self._confirmations.approve_click(self._items[-1].id)

    def _reject(self) -> None:
        if self._items:
            self._confirmations.reject_click(self._items[-1].id)
