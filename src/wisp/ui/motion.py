"""Motion: short, purposeful animations that respect the user's choice (D-044).

Only state changes animate (windows and panels opening/closing, Island expand/collapse, tab
switches, new transcript rows, toggles), for 120–250 ms with an ease-out curve; nothing loops
while idle except the orb's slow glow. Motion is off when Windows' "Animation effects" is off
(SystemParametersInfoW SPI_GETCLIENTAREAANIMATION, 0x1042, BOOL) or when Settings → Loadout →
"Reduce motion" is on; then every helper jumps straight to the end state.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QObject, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

FAST_MS = 120
NORMAL_MS = 180
SLOW_MS = 250
EASING = QEasingCurve.Type.OutCubic
SPI_GETCLIENTAREAANIMATION = 0x1042

_reduce_motion = False
_forced: bool | None = None  # tests pin motion on or off


def system_animations_enabled() -> bool:
    try:
        value = wintypes.BOOL(True)
        ok = ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0,
                                                        ctypes.byref(value), 0)
        return bool(value.value) if ok else True
    except (AttributeError, OSError):
        return True


def configure(reduce_motion: bool) -> None:
    global _reduce_motion
    _reduce_motion = reduce_motion


def force(enabled: bool | None) -> None:
    """Tests only: pin motion on/off (None = follow settings and Windows)."""
    global _forced
    _forced = enabled


def enabled() -> bool:
    if _forced is not None:
        return _forced
    return not _reduce_motion and system_animations_enabled()


def animate(target: QObject, prop: bytes, start, end, duration: int = NORMAL_MS,
            finished: Callable[[], None] | None = None) -> QPropertyAnimation | None:
    """Animate ``target.prop`` from ``start`` to ``end``; with motion off, jump to ``end``."""
    if not enabled():
        target.setProperty(prop.decode(), end)
        if finished is not None:
            finished()
        return None
    animation = QPropertyAnimation(target, prop, target)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(EASING)
    if finished is not None:
        animation.finished.connect(finished)
    animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return animation


def fade_in(widget: QWidget, duration: int = NORMAL_MS) -> None:
    """Fade a child widget in; the opacity effect is removed afterwards (no lasting cost)."""
    if not enabled():
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    animate(effect, b"opacity", 0.0, 1.0, duration,
            finished=lambda: widget.setGraphicsEffect(None))


def window_fade(window: QWidget, show: bool, duration: int = FAST_MS,
                finished: Callable[[], None] | None = None) -> None:
    """Fade a top-level window in (after show) or out (then ``finished`` hides it)."""
    if not enabled():
        window.setWindowOpacity(1.0)
        if finished is not None:
            finished()
        return
    start, end = (0.0, 1.0) if show else (window.windowOpacity(), 0.0)
    window.setWindowOpacity(start)

    def done() -> None:
        if finished is not None:
            finished()
        window.setWindowOpacity(1.0)

    animate(window, b"windowOpacity", start, end, duration, finished=done)
