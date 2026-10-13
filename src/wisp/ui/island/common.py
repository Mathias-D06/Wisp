"""Shared Island pieces: icon names (Lucide, ``ui/iconset.py``), small widgets and a background
runner that keeps blocking Windows calls off the UI thread."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from wisp.ui import iconset, theme
from wisp.ui.widgets import IconButton

log = logging.getLogger(__name__)

PLAY, PAUSE, NEXT, PREVIOUS = "play", "pause", "next", "previous"
VOLUME, MUTE, WIFI, BLUETOOTH = "volume", "mute", "wifi", "bluetooth"
BRIGHTNESS, NIGHT, THEME, SLEEP = "brightness", "night", "theme", "sleep"
LOCK, POWER, RESTART = "lock", "power", "restart"
PASTE, APPS, CALENDAR, CHART, PHOTO = "clipboard", "apps", "calendar", "chart", "image"
SETTINGS, DELETE, ADD, PIN, SEARCH, MIC = "settings", "delete", "add", "pin", "search", "mic"


def glyph_icon(name: str, color: str, size: int = theme.ICON_SM) -> QIcon:
    """A theme-tinted line icon (``size`` is kept for callers; icons draw at any size)."""
    return iconset.icon(name, color, disabled=theme.current().muted)


class GlyphButton(IconButton):
    """Square icon button used across the Island (same icon size everywhere)."""

    def __init__(self, name: str, tooltip: str, size: int = 34, parent=None):
        super().__init__(name, tooltip, theme.ICON_SM, parent=parent)
        self.setFixedSize(size, size)


class Chip(QPushButton):
    """Checkable tile with an icon and a label (Wi-Fi, Bluetooth …)."""

    def __init__(self, name: str, label: str, color: str | None = None, parent=None):
        super().__init__(label, parent)
        self.setObjectName("Chip")
        self._name = name
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setIconSize(QSize(theme.ICON_SM, theme.ICON_SM))
        theme.signals.changed.connect(self._tint)  # bound: dropped when the chip is deleted
        self._tint()

    def _tint(self, _palette=None) -> None:
        p = theme.palette_for(self)
        self.setIcon(iconset.icon(self._name, p.secondary, disabled=p.muted, checked=p.accent))


def section(text: str) -> QLabel:
    label = QLabel(text)  # sentence case (Windows typography guidance)
    label.setObjectName("Section")
    return label


class BarChart(QWidget):
    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self.accent = QColor(accent)
        self.setFont(theme.ui_font(theme.CAPTION))
        self.values: list[tuple[str, float]] = []
        self.setMinimumHeight(110)

    def set_values(self, values: list[tuple[str, float]]) -> None:
        self.values = values
        self.update()

    def paintEvent(self, _event) -> None:
        if not self.values:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        peak = max(v for _, v in self.values) or 1
        width = self.width() / len(self.values)
        label_h = 18
        for index, (label, value) in enumerate(self.values):
            bar_h = (self.height() - label_h - 6) * (value / peak)
            rect = QRectF(index * width + width * 0.2, self.height() - label_h - bar_h,
                          width * 0.6, bar_h)
            color = QColor(self.accent)
            color.setAlpha(255 if index == len(self.values) - 1 else 150)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(self.palette().color(self.foregroundRole()))
            painter.drawText(QRectF(index * width, self.height() - label_h, width, label_h),
                             Qt.AlignmentFlag.AlignCenter, label)
        painter.end()


def _com_init() -> None:
    try:
        import pythoncom

        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    except Exception as exc:
        log.debug("COM init skipped: %s", exc)


class Background(QObject):
    """Run blocking calls on COM-ready worker threads; deliver results on the Qt thread."""

    _done = Signal(object, object, object)

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None):
        super().__init__()
        self.loop = loop
        self._pool = concurrent.futures.ThreadPoolExecutor(3, "island", initializer=_com_init)
        self._done.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def run(self, fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None,
            on_error: Callable[[Exception], None] | None = None) -> None:
        def work() -> None:
            try:
                self._done.emit(on_done, fn(), None)
            except Exception as exc:
                log.warning("Background task failed: %s", exc)
                self._done.emit(on_error, None, exc)

        self._pool.submit(work)

    def run_coro(self, coro, on_done: Callable[[Any], None] | None = None,
                 on_error: Callable[[Exception], None] | None = None) -> None:
        if self.loop is None:
            coro.close()
            return
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def finished(fut: concurrent.futures.Future) -> None:
            exc = fut.exception()
            if exc is not None:
                log.warning("Background coroutine failed: %s", exc)
                self._done.emit(on_error, None, exc)
            else:
                self._done.emit(on_done, fut.result(), None)

        future.add_done_callback(finished)

    @staticmethod
    def _deliver(callback, result, error) -> None:
        if callback is None:
            return
        callback(error if error is not None else result)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
