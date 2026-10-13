"""Window chrome for Wisp's framed windows (console, Settings; D-042): Mica through the whole
window on Windows 11 22H2+ (the window's own background stays transparent and the panels paint
on top), otherwise a dark/light title bar and rounded corners over the solid theme background.
Call ``prepare`` before the window is first shown and ``apply`` once it has a native handle.
``WISP_NO_MICA=1`` forces the solid fallback (troubleshooting, off-screen screenshots)."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QWidget

from wisp.ui import theme
from wisp.winapi import dwm


def mica_wanted() -> bool:
    return dwm.mica_supported() and os.environ.get("WISP_NO_MICA") != "1"


class _ThemeHook(QObject):
    """Re-applies the chrome when the theme changes. A child of the window, so Qt drops the
    connection when the window is destroyed (a lambda would keep it, and the window, alive)."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.setObjectName("ChromeThemeHook")
        theme.signals.changed.connect(self.on_theme)

    def on_theme(self, p: theme.Palette) -> None:
        apply(self.parent(), p)


def prepare(window: QWidget) -> None:
    if mica_wanted():
        window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        window.setProperty("mica", True)
    if window.findChild(QObject, "ChromeThemeHook") is None:
        _ThemeHook(window)


def apply(window: QWidget, p: theme.Palette | None = None) -> None:
    p = p or theme.current()
    hwnd = int(window.winId())
    mica = bool(window.property("mica"))
    dwm.style_window(hwnd, dark=p.dark, backdrop=mica)
    if mica:
        dwm.extend_frame(hwnd)
