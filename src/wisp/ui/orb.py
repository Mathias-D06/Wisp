"""The orb: Wisp's one living element and a click-to-talk button (D-044).

Ready: a very slow, gentle glow. Listening: grows with the microphone level. Thinking: a soft
pulse. Speaking: follows the output level. Offline/error: still, in a muted/red tone. Colours
come from the theme tokens. The frame timer runs only while the orb is visible and only as fast
as the state needs (8 fps for the slow glow, 60 fps while listening, thinking or speaking); with
motion off the orb is drawn once per state change.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from wisp.ui import motion, theme

TOOLTIPS = {
    "idle": "Click to talk",
    "listening": "Listening — click to stop",
    "thinking": "Thinking…",
    "speaking": "Speaking — click to interrupt",
    "offline": "Offline",
    "error": "Needs attention",
}
FRAME_MS = {"idle": 125, "listening": 16, "speaking": 16, "thinking": 16}
"""Ready breathes over 4.5 s, so 8 fps is smooth there and keeps idle CPU low; states that react
to sound or pulse run at 60 fps."""
GLOW_PERIOD_S = 4.5
PULSE_PERIOD_S = 1.4


def state_color(state: str, accent: str, p: theme.Palette | None = None) -> QColor:
    p = p or theme.current()
    return QColor({"listening": p.success, "thinking": p.warning, "offline": p.muted,
                   "error": p.danger}.get(state, accent))


def paint_orb(painter: QPainter, size: float, color: QColor, glow: float, scale: float) -> None:
    """Draw the orb mark centred in a ``size`` square: a soft halo (``glow`` 0–1) and a
    shaded core scaled by ``scale``."""
    center = QPointF(size / 2, size / 2)
    core = size * 0.30 * scale
    painter.setPen(Qt.PenStyle.NoPen)
    if glow > 0.01:
        halo = QRadialGradient(center, size / 2)
        inner = QColor(color)
        inner.setAlphaF(min(1.0, 0.55 * glow))
        outer = QColor(color)
        outer.setAlphaF(0.0)
        halo.setColorAt(core / (size / 2) * 0.85, inner)
        halo.setColorAt(1.0, outer)
        painter.setBrush(halo)
        painter.drawEllipse(center, size / 2, size / 2)
    shade = QRadialGradient(QPointF(center.x() - core * 0.35, center.y() - core * 0.4), core * 1.6)
    shade.setColorAt(0.0, color.lighter(160))
    shade.setColorAt(0.55, color)
    shade.setColorAt(1.0, color.darker(150))
    painter.setBrush(shade)
    painter.drawEllipse(center, core, core)


class Orb(QWidget):
    clicked = Signal()

    def __init__(self, size: int = 28, accent: str | None = None, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._accent = accent or theme.current().accent
        self.state = "idle"
        self.level = 0.0
        self._smoothed = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self.setToolTip(TOOLTIPS["idle"])
        self.setAccessibleName("Wisp — click to talk")

    # ----- state -------------------------------------------------------------------------------
    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self.update()

    def set_state(self, state: str, level: float = 0.0) -> None:
        changed = state != self.state
        self.level = level
        if changed:
            self.state = state
            self.setToolTip(TOOLTIPS.get(state, state))
            self._schedule()
            self.update()

    def _schedule(self) -> None:
        interval = FRAME_MS.get(self.state)
        if interval is None or not motion.enabled() or not self.isVisible():
            self._timer.stop()
        elif self._timer.interval() != interval or not self._timer.isActive():
            self._timer.start(interval)

    def showEvent(self, event) -> None:
        self._schedule()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    @property
    def animating(self) -> bool:
        return self._timer.isActive()

    # ----- input -------------------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """Qt reports a double-click as a second press; one toggle per double-click is enough
        (two would start and immediately stop listening)."""
        event.accept()

    # ----- drawing -----------------------------------------------------------------------------
    def frame(self, now: float) -> tuple[float, float]:
        """(glow 0–1, core scale) for the current state at time ``now``."""
        moving = motion.enabled()
        self._smoothed += (min(1.0, self.level * 1.6) - self._smoothed) * 0.35
        if self.state == "idle":
            breath = 0.5 + 0.5 * math.sin(2 * math.pi * now / GLOW_PERIOD_S) if moving else 0.5
            return 0.25 + 0.2 * breath, 1.0
        if self.state in ("listening", "speaking"):
            level = self._smoothed if moving else 0.0
            return 0.45 + 0.5 * level, 1.0 + 0.22 * level
        if self.state == "thinking":
            pulse = 0.5 + 0.5 * math.sin(2 * math.pi * now / PULSE_PERIOD_S) if moving else 0.5
            return 0.3 + 0.35 * pulse, 1.0 + 0.04 * pulse
        return 0.0, 0.92  # offline / error: still

    def paintEvent(self, _event) -> None:
        glow, scale = self.frame(time.monotonic())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_orb(painter, self.width(), state_color(self.state, self._accent), glow, scale)
        painter.end()
