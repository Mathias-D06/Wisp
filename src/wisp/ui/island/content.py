"""What the island draws inside its shape (D-045): compact activities, the split circle and
banners, painted with QPainter so that content can fade and scale while the shape morphs.

The island is black in either theme, so colours come from the dark palette (``Look.palette``).
Every function draws into ``rect`` (the current shape) and never outside it.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPixmap

from wisp.ui import iconset, theme
from wisp.ui.island.machine import Activity, Banner, Presentation
from wisp.ui.orb import orb_look, paint_orb, state_color

ORB_STATES = {"listening": "listening", "thinking": "thinking", "speaking": "speaking"}
TONE_ICONS = {"success": "check", "warning": "warning", "danger": "error", "muted": "info",
              "accent": "info"}
BARS = 5
WAVE_BARS = 12


class LevelHistory:
    """Recent 0–1 levels for waveforms and bars (newest last)."""

    def __init__(self, size: int = WAVE_BARS):
        self.values: deque[float] = deque([0.0] * size, maxlen=size)

    def push(self, level: float) -> None:
        self.values.append(max(0.0, min(1.0, level)))

    def latest(self) -> float:
        return self.values[-1]


@dataclass
class Look:
    """Everything the painters need besides the presentation."""

    palette: theme.Palette
    now: float = field(default_factory=time.monotonic)
    wall: float = field(default_factory=time.time)  # for countdowns (epoch seconds)
    moving: bool = True  # motion allowed
    orb_state: str = "idle"  # the voice controller's orb state when no activity says otherwise
    orb_level: float = 0.0
    mic: LevelHistory = field(default_factory=LevelHistory)
    output: LevelHistory = field(default_factory=lambda: LevelHistory(BARS))
    media: LevelHistory = field(default_factory=lambda: LevelHistory(BARS))
    dictation: LevelHistory = field(default_factory=LevelHistory)
    art: QPixmap | None = None
    reply: str = ""  # Wisp's latest words, for the speaking state
    hover: bool = False
    muted: bool = False


def tone_color(tone: str, palette: theme.Palette) -> QColor:
    return QColor({"success": palette.success, "warning": palette.warning,
                   "danger": palette.danger, "muted": palette.muted}.get(tone, palette.accent))


def _font(size: int, weight: int = theme.REGULAR) -> QFont:
    return theme.ui_font(size, weight)


def _text(painter: QPainter, rect: QRectF, text: str, color: str | QColor, size: int,
          align=Qt.AlignmentFlag.AlignLeft, weight: int = theme.REGULAR) -> None:
    font = _font(size, weight)
    painter.setFont(font)
    painter.setPen(QColor(color))
    elided = QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width()))
    painter.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, elided)


def _orb(painter: QPainter, center: QPointF, size: float, color: QColor, look: Look,
         state: str, level: float) -> None:
    glow, scale = orb_look(state, look.now, level, look.moving)
    painter.save()
    painter.translate(center.x() - size / 2, center.y() - size / 2)
    paint_orb(painter, size, color, glow, scale)
    painter.restore()


def _bars(painter: QPainter, rect: QRectF, levels, color: QColor, moving: bool,
          gap: float = 3.0) -> None:
    """Vertical rounded bars, centred; with motion off they rest at a neutral height."""
    values = list(levels) if moving else [0.35] * len(levels)
    count = len(values)
    width = max(2.0, (rect.width() - gap * (count - 1)) / count)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    for index, value in enumerate(values):
        height = max(width, rect.height() * (0.18 + 0.82 * value))
        x = rect.left() + index * (width + gap)
        bar = QRectF(x, rect.center().y() - height / 2, width, height)
        painter.drawRoundedRect(bar, width / 2, width / 2)


def _icon(painter: QPainter, rect: QRectF, name: str, color: QColor) -> None:
    iconset.icon(name, color.name()).paint(painter, rect.toAlignedRect())


def _art(painter: QPainter, rect: QRectF, art: QPixmap | None, look: Look, round_: bool) -> None:
    radius = rect.width() / 2 if round_ else rect.width() * 0.22
    if art is None or art.isNull():
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(look.palette.surface2))
        painter.drawRoundedRect(rect, radius, radius)
        _icon(painter, rect.adjusted(rect.width() * 0.22, rect.height() * 0.22,
                                     -rect.width() * 0.22, -rect.height() * 0.22),
              "speaking", QColor(look.palette.secondary))
        return
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.save()
    painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
    painter.drawPixmap(rect, art, QRectF(art.rect()))
    painter.restore()


def countdown_text(due: float, wall: float) -> str:
    left = max(0, int(due - wall + 0.999))
    hours, rest = divmod(left, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


# ----- compact shapes ---------------------------------------------------------------------------
def paint_idle(painter: QPainter, rect: QRectF, look: Look) -> None:
    pad = rect.height() * 0.3
    size = rect.height() * 0.5
    color = state_color(look.orb_state, look.palette.accent, look.palette)
    _orb(painter, QPointF(rect.left() + pad + size / 2, rect.center().y()), size, color, look,
         look.orb_state if look.orb_state in ("idle", "offline", "error") else "idle", 0.0)
    if look.muted:
        icon = QRectF(rect.right() - pad - size, rect.center().y() - size / 2, size, size)
        _icon(painter, icon, "mic-off", QColor(look.palette.muted))


def paint_activity(painter: QPainter, rect: QRectF, activity: Activity, look: Look) -> None:
    p = look.palette
    h = rect.height()
    pad = h * 0.3
    lead = h * 0.5  # orb / icon size
    left = QRectF(rect.left() + pad, rect.center().y() - lead / 2, lead, lead)
    right_w = h * 1.1
    right = QRectF(rect.right() - pad - right_w, rect.top() + h * 0.28, right_w, h * 0.44)
    text_rect = QRectF(left.right() + pad * 0.8, rect.top(), right.left() - left.right()
                       - pad * 1.6, h)
    kind = activity.kind
    if kind in ORB_STATES:
        color = state_color(kind, p.accent, p)
        level = look.mic.latest() if kind == "listening" else look.output.latest()
        _orb(painter, left.center(), lead, color, look, kind, level)
        if kind == "listening":
            _bars(painter, QRectF(right.left() - right_w * 0.6, right.top(), right_w * 1.6,
                                  right.height()), look.mic.values, color, look.moving, 2.0)
            _text(painter, text_rect.adjusted(0, 0, -right_w * 0.6, 0),
                  activity.text or "Listening…", p.secondary, theme.BODY)
        elif kind == "thinking":
            _text(painter, text_rect.adjusted(0, 0, right.width() + pad, 0),
                  activity.text or "Thinking…", p.secondary, theme.BODY)
        else:
            _bars(painter, right, look.output.values, color, look.moving)
            _text(painter, text_rect, first_words(look.reply) or activity.text or "Speaking",
                  p.text, theme.BODY)
        return
    if kind == "dictation":
        color = tone_color(activity.tone, p)
        _icon(painter, left, "mic", color)
        if activity.meter:
            _bars(painter, right, list(look.dictation.values)[-BARS:], color, look.moving)
        else:
            text_rect = text_rect.adjusted(0, 0, right.width() + pad, 0)
        _text(painter, text_rect, activity.text, p.text, theme.BODY)
        return
    if kind == "music":
        art = QRectF(rect.left() + pad * 0.7, rect.center().y() - h * 0.32, h * 0.64, h * 0.64)
        _art(painter, art, look.art, look, round_=False)
        state = activity.data
        text_rect = QRectF(art.right() + pad * 0.8, rect.top(), right.left() - art.right()
                           - pad * 1.6, h)
        _text(painter, text_rect, getattr(state, "title", "") or activity.text, p.text,
              theme.CAPTION)
        if look.hover:
            icon = QRectF(right.center().x() - lead / 2, rect.center().y() - lead / 2, lead, lead)
            _icon(painter, icon, "pause", QColor(p.text))
        else:
            _bars(painter, right, look.media.values, QColor(p.accent), look.moving)
        return
    if kind == "countdown":
        _icon(painter, left, "calendar", QColor(p.warning))
        due = activity.data if isinstance(activity.data, (int, float)) else look.wall
        clock = countdown_text(due, look.wall)
        clock_rect = QRectF(rect.right() - pad - h * 1.9, rect.top(), h * 1.9, h)
        _text(painter, clock_rect, clock, p.warning, theme.BODY, Qt.AlignmentFlag.AlignRight)
        _text(painter, QRectF(text_rect.left(), rect.top(), clock_rect.left() - text_rect.left()
                              - pad * 0.5, h), activity.text, p.text, theme.BODY)
        return
    color = tone_color(activity.tone, p)  # status
    _icon(painter, left, TONE_ICONS.get(activity.tone, "info"), color)
    _text(painter, text_rect.adjusted(0, 0, right.width() + pad, 0), activity.text, p.text,
          theme.BODY)


def paint_secondary(painter: QPainter, circle: QRectF, activity: Activity, look: Look) -> None:
    """The split's detached circle: one glance at the second activity."""
    p = look.palette
    inner = circle.adjusted(circle.width() * 0.2, circle.height() * 0.2,
                            -circle.width() * 0.2, -circle.height() * 0.2)
    if activity.kind == "music":
        _art(painter, circle.adjusted(3, 3, -3, -3), look.art, look, round_=True)
    elif activity.kind in ORB_STATES:
        level = look.mic.latest() if activity.kind == "listening" else look.output.latest()
        _orb(painter, circle.center(), inner.width() * 1.2,
             state_color(activity.kind, p.accent, p), look, activity.kind, level)
    elif activity.kind == "countdown":
        due = activity.data if isinstance(activity.data, (int, float)) else look.wall
        minutes = max(0, int((due - look.wall + 59) // 60))
        _text(painter, circle, f"{minutes}m", p.warning, theme.CAPTION,
              Qt.AlignmentFlag.AlignHCenter)
    else:
        _icon(painter, inner, "mic", tone_color(activity.tone, p))


def paint_banner(painter: QPainter, rect: QRectF, banner: Banner, look: Look) -> None:
    p = look.palette
    pad = theme.SPACE["l"]
    badge = 40.0
    circle = QRectF(rect.left() + pad, rect.center().y() - badge / 2, badge, badge)
    color = tone_color(banner.tone, p)
    tint = QColor(color)
    tint.setAlphaF(0.18)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tint)
    painter.drawEllipse(circle)
    _icon(painter, circle.adjusted(10, 10, -10, -10), banner.icon, color)
    text_left = circle.right() + theme.SPACE["m"]
    width = rect.right() - pad - text_left
    if banner.line:
        _text(painter, QRectF(text_left, rect.center().y() - 21, width, 22), banner.title, p.text,
              theme.TITLE, weight=theme.SEMIBOLD)
        _text(painter, QRectF(text_left, rect.center().y() + 1, width, 20), banner.line,
              p.secondary, theme.CAPTION)
    else:
        _text(painter, QRectF(text_left, rect.top(), width, rect.height()), banner.title, p.text,
              theme.TITLE, weight=theme.SEMIBOLD)


def paint_compact(painter: QPainter, rect: QRectF, circle: QRectF | None, p: Presentation,
                  look: Look) -> None:
    """Content for every non-expanded presentation."""
    if p.mode == "banner" and p.banner is not None:
        paint_banner(painter, rect, p.banner, look)
    elif p.mode == "activity" and p.main is not None:
        paint_activity(painter, rect, p.main, look)
        if circle is not None and p.secondary is not None:
            paint_secondary(painter, circle, p.secondary, look)
    elif p.mode == "idle":
        paint_idle(painter, rect, look)


def first_words(text: str, limit: int = 60) -> str:
    """The start of Wisp's reply for the speaking state (the view elides to fit)."""
    text = " ".join(text.split())
    return text[:limit]
