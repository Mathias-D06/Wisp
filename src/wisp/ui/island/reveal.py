"""Bringing the auto-hidden island back (D-049): a small hot zone at the top-centre edge of its
display, and a short dwell so a pointer passing over browser tabs doesn't trigger it.

Coordinates are Qt's device-independent pixels (QScreen.geometry, QCursor.pos; Qt reads the
cursor with GetCursorPos and maps it per display), so the zone is the same size on screen at any
scaling and follows each display's own scale factor.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect

from wisp.ui.theme import ISLAND, IslandTokens


def hot_zone(screen: QRect, tokens: IslandTokens = ISLAND) -> QRect:
    """The idle pill's width plus ``reveal_margin`` on each side, and the top ``reveal_height``
    px of ``screen`` (its full geometry: the zone is the very edge, even over a top taskbar)."""
    width = tokens.idle[0] + 2 * tokens.reveal_margin
    left = screen.x() + (screen.width() - width) // 2
    return QRect(left, screen.y(), width, tokens.reveal_height)


def in_zone(point: QPoint, zone: QRect) -> bool:
    return zone.contains(point)


class Dwell:
    """True once the pointer has stayed inside for ``ms`` without leaving."""

    def __init__(self, ms: int = ISLAND.reveal_dwell_ms):
        self.ms = ms
        self._since: float | None = None

    def update(self, inside: bool, now: float) -> bool:
        if not inside:
            self._since = None
            return False
        if self._since is None:
            self._since = now
        return (now - self._since) * 1000 >= self.ms

    def reset(self) -> None:
        self._since = None
