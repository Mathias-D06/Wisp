"""System tray icon: state at a glance, menu for every main surface, toast notifications.

Toasts use ``QSystemTrayIcon.showMessage``, which Windows shows as a notification
(https://doc.qt.io/qt-6/qsystemtrayicon.html).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from wisp.ui.icons import orb_icon


class Tray:
    def __init__(self, accent: str):
        self._accent = accent
        self._state = "idle"
        self.icon = QSystemTrayIcon(orb_icon(accent))
        self.icon.setToolTip("Wisp")
        self.menu = QMenu()
        self.icon.setContextMenu(self.menu)
        self._on_click: Callable[[], None] | None = None
        self.icon.activated.connect(self._activated)

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def on_click(self, callback: Callable[[], None]) -> None:
        self._on_click = callback

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger and self._on_click:
            self._on_click()

    def add_action(
        self, text: str, callback: Callable[[], None] | Callable[[bool], None], checkable=False
    ) -> QAction:
        action = QAction(text, self.menu)
        action.setCheckable(checkable)
        if checkable:
            action.toggled.connect(callback)
        else:
            action.triggered.connect(lambda _checked=False: callback())
        self.menu.addAction(action)
        return action

    def add_separator(self) -> None:
        self.menu.addSeparator()

    def set_state(self, state: str, tooltip: str) -> None:
        if state != self._state:
            self._state = state
            self.icon.setIcon(orb_icon(self._accent, state))
        self.icon.setToolTip(f"Wisp — {tooltip}"[:120])

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self.icon.setIcon(orb_icon(accent, self._state))

    def notify(self, title: str, message: str, msecs: int = 6000) -> None:
        self.icon.showMessage(title, message, orb_icon(self._accent), msecs)
