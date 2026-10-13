"""Line icons: Lucide 1.56.0 (ISC; icons derived from Feather also MIT; both texts in
assets/icons/LICENSE-lucide.txt; D-043).

Icons are SVG, tinted from the theme and drawn as vectors at whatever size and device pixel
ratio Qt asks for, so they stay sharp at 100 %, 125 %, 150 % and 200 % scaling. The stroke is
normalised so every icon has the same visual weight (1.5 device-independent pixels) whatever
size it is drawn at.
"""

from __future__ import annotations

import functools
from pathlib import Path

from PySide6.QtCore import QByteArray, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
STROKE_PX = 1.5  # visual stroke width in device-independent pixels
GRID = 24  # Lucide's viewBox

# Names used by the UI → Lucide file names.
ICONS = {
    "play": "play", "pause": "pause", "next": "skip-forward", "previous": "skip-back",
    "volume": "volume-2", "mute": "volume-x", "wifi": "wifi", "wifi-off": "wifi-off",
    "bluetooth": "bluetooth", "brightness": "sun", "night": "moon", "theme": "sun-moon",
    "lock": "lock", "power": "power", "restart": "rotate-ccw", "sleep": "moon",
    "clipboard": "clipboard", "apps": "layout-grid", "calendar": "calendar-clock",
    "chart": "chart-column", "image": "image", "settings": "settings", "delete": "trash-2",
    "add": "plus", "pin": "pin", "search": "search", "mic": "mic", "mic-off": "mic-off",
    "info": "info", "warning": "triangle-alert", "error": "circle-alert", "check": "check",
    "chevron-down": "chevron-down", "chevron-up": "chevron-up", "close": "x",
    "send": "send-horizontal", "retry": "refresh-cw", "folder": "folder-open",
    "listen": "ear", "today": "list-checks", "controls": "sliders-horizontal",
    "speaking": "audio-lines", "copy": "copy",
}


@functools.cache
def _source(name: str) -> str:
    return (ICON_DIR / f"{ICONS.get(name, name)}.svg").read_text(encoding="utf-8")


def svg_text(name: str, color: str, size: float) -> str:
    """The icon's SVG with its colour and a stroke that renders 1.5 px wide at ``size``."""
    stroke = STROKE_PX * GRID / max(size, 1.0)
    text = _source(name).replace("currentColor", QColor(color).name())
    return text.replace('stroke-width="2"', f'stroke-width="{stroke:.3f}"')


@functools.lru_cache(maxsize=512)
def _renderer(name: str, color: str, size: int) -> QSvgRenderer:
    return QSvgRenderer(QByteArray(svg_text(name, color, size).encode("utf-8")))


class SvgIconEngine(QIconEngine):
    """Paints the SVG directly, so QIcon is sharp at any size and device pixel ratio."""

    def __init__(self, name: str, color: str, disabled_color: str | None = None,
                 checked_color: str | None = None):
        super().__init__()
        self.name, self.color = name, color
        self.disabled_color = disabled_color or color
        self.checked_color = checked_color or color

    def _color(self, mode: QIcon.Mode, state: QIcon.State) -> str:
        if mode == QIcon.Mode.Disabled:
            return self.disabled_color
        if state == QIcon.State.On:
            return self.checked_color
        return self.color

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        side = min(rect.width(), rect.height())
        target = QRectF(rect.x() + (rect.width() - side) / 2, rect.y() + (rect.height() - side) / 2,
                        side, side)
        _renderer(self.name, self._color(mode, state), side).render(painter, target)

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State,
                     scale: float) -> QPixmap:
        pixmap = QPixmap(QSize(round(size.width() * scale), round(size.height() * scale)))
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint(painter, QRect(0, 0, size.width(), size.height()), mode, state)
        painter.end()
        return pixmap

    def clone(self) -> SvgIconEngine:
        return SvgIconEngine(self.name, self.color, self.disabled_color, self.checked_color)


def icon(name: str, color: str, disabled: str | None = None, checked: str | None = None) -> QIcon:
    return QIcon(SvgIconEngine(name, color, disabled, checked))


def write_tinted(name: str, color: str, folder: Path, size: int = 16) -> Path:
    """A tinted copy on disk, for Qt stylesheet ``image: url(...)`` (check marks, arrows)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}-{QColor(color).name()[1:]}-{size}.svg"
    if not path.exists():
        path.write_text(svg_text(name, color, size), encoding="utf-8")
    return path
