"""The island (D-045): one black, Dynamic Island-style surface at the top centre of the screen
that morphs to show what Wisp is doing: idle pill, live activities (listening, thinking, speaking,
dictation, music, countdown), a split when two run at once, banners for events, and the expanded
panel with the conversation and the tabs.

Window: a fixed transparent canvas big enough for the largest state (the native window is never
resized), frameless, always on top, a tool window (no taskbar button, no Alt+Tab entry), shown
without activating and WS_EX_NOACTIVATE (clicking it never takes focus; the text boxes take it on
purpose when clicked). The shape is painted with QPainter and its input region follows the shape
(QWindow.setMask), so clicks beside it reach the app underneath. The soft shadow lives in a
separate click-through window behind it.

Motion: width, height and the split circle are springs (spring.py) driven by one frame timer
that runs only while something moves; the corner radius follows the height (a capsule while
compact). Content fades and scales between states. With motion off, the shape jumps and the
content crossfades.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QLineEdit, QMenu, QTextEdit, QWidget

from wisp.ui import motion, theme
from wisp.ui.island import content, geometry
from wisp.ui.island.common import Chip
from wisp.ui.island.machine import IslandStateMachine, Presentation
from wisp.ui.island.panel import ExpandedPanel, island_stylesheet
from wisp.ui.island.reveal import Dwell, hot_zone, in_zone
from wisp.ui.island.spring import SpringSet
from wisp.ui.theme import ISLAND
from wisp.ui.widgets import IconButton
from wisp.winapi import fullscreen
from wisp.winapi import windows as win

log = logging.getLogger(__name__)

FLAGS = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
         | Qt.WindowType.WindowStaysOnTopHint)
EDITABLE = (QLineEdit, QTextEdit, QAbstractSpinBox)
COMPACT = ("idle", "activity")
VK_LBUTTON, VK_RBUTTON = 0x01, 0x02
SWIPE_PX = 18
SHADOW_OFFSET = 6
MOVING_KINDS = ("listening", "speaking", "dictation", "thinking")


def ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) ** 3


@dataclass
class Layer:
    """One state's content while it fades in or out."""

    p: Presentation
    start: float  # when the fade-in starts (monotonic seconds)
    in_ms: float
    scale_from: float  # incoming content grows from this scale (1.0: no scaling)
    end: float | None = None  # when the fade-out started
    out_ms: float = ISLAND.content_out_ms
    snapshot: QPixmap | None = None  # the expanded panel while the shape morphs
    rows: list[QRect] = field(default_factory=list)

    def alpha(self, now: float, delay_ms: float = 0.0) -> float:
        a = ease_out((now - self.start) * 1000 / self.in_ms - delay_ms / self.in_ms)
        if self.end is not None:
            a *= 1.0 - ease_out((now - self.end) * 1000 / max(1.0, self.out_ms))
        return a

    def scale(self, now: float) -> float:
        grown = self.scale_from + (1.0 - self.scale_from) * ease_out(
            (now - self.start) * 1000 / self.in_ms)
        if self.end is None:
            return grown
        shrink = ease_out((now - self.end) * 1000 / max(1.0, self.out_ms))
        return grown - (1.0 - ISLAND.content_scale) * shrink

    def finished(self, now: float) -> bool:
        return self.end is not None and (now - self.end) * 1000 >= self.out_ms

    def entering(self, now: float) -> bool:
        stagger = ISLAND.row_stagger_ms * max(0, len(self.rows) - 1)
        return (now - self.start) * 1000 < self.in_ms + stagger


# ----- the shadow --------------------------------------------------------------------------------
def shadow_tile(radius: int, blur: int, alpha: int) -> QImage:
    """A blurred rounded square for nine-slice drawing: corners are (radius + 2·blur) wide."""
    from PIL import Image, ImageDraw, ImageFilter

    extent = 2 * blur
    corner = radius + extent
    side = 2 * corner + 1
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle((extent, extent, side - 1 - extent, side - 1 - extent),
                                           radius, fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(blur / 2))
    rgba = Image.merge("RGBA", (*(Image.new("L", mask.size, 0),) * 3, mask))
    data = rgba.tobytes()
    return QImage(data, side, side, side * 4, QImage.Format.Format_RGBA8888).copy()


class ShadowLayer(QWidget):
    """The island's soft shadow, in its own window that never takes input (WS_EX_TRANSPARENT via
    Qt::WindowTransparentForInput), so it can't catch clicks meant for the app underneath."""

    def __init__(self, size) -> None:
        super().__init__(None, FLAGS | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Wisp Island shadow")
        self.setFixedSize(size)
        self.rect_ = QRectF()
        self.strength = 0.0
        self._tile = shadow_tile(ISLAND.expanded_radius, ISLAND.shadow_blur, ISLAND.shadow_alpha)

    def outer(self, rect: QRectF) -> QRectF:
        e = 2 * ISLAND.shadow_blur
        return rect.adjusted(-e, -e + SHADOW_OFFSET, e, e + SHADOW_OFFSET)

    def set_shape(self, rect: QRectF, strength: float) -> None:
        strength = round(strength, 3)
        if rect == self.rect_ and strength == self.strength:
            return
        dirty = self.outer(self.rect_).united(self.outer(rect))
        self.rect_, self.strength = QRectF(rect), strength
        self.update(dirty.toAlignedRect().adjusted(-2, -2, 2, 2))

    def paintEvent(self, _event) -> None:
        if self.strength <= 0 or self.rect_.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(self.strength)
        draw_nine_slice(painter, self.outer(self.rect_), self._tile)
        painter.end()


def draw_nine_slice(painter: QPainter, outer: QRectF, tile: QImage) -> None:
    c = (tile.width() - 1) / 2  # corner size
    mid_w, mid_h = outer.width() - 2 * c, outer.height() - 2 * c
    x0, y0, x1, y1 = outer.left(), outer.top(), outer.right() - c, outer.bottom() - c
    for tx, ty, sx, sy in ((x0, y0, 0, 0), (x1, y0, c + 1, 0), (x0, y1, 0, c + 1),
                           (x1, y1, c + 1, c + 1)):
        painter.drawImage(QRectF(tx, ty, c, c), tile, QRectF(sx, sy, c, c))
    if mid_w > 0:
        painter.drawImage(QRectF(x0 + c, y0, mid_w, c), tile, QRectF(c, 0, 1, c))
        painter.drawImage(QRectF(x0 + c, y1, mid_w, c), tile, QRectF(c, c + 1, 1, c))
    if mid_h > 0:
        painter.drawImage(QRectF(x0, y0 + c, c, mid_h), tile, QRectF(0, c, c, 1))
        painter.drawImage(QRectF(x1, y0 + c, c, mid_h), tile, QRectF(c + 1, c, c, 1))


# ----- the island --------------------------------------------------------------------------------
class Island(QWidget):
    settings_requested = Signal(str)
    console_requested = Signal()
    quit_requested = Signal()
    files_dropped = Signal(list)  # paths dropped on the island: they go on the shelf (D-051)
    watch_stop_requested = Signal()  # a click on the "Watching" activity's right half (D-052)
    drop_tab = "Files & Share"

    def __init__(self, voice, accent: str, has_key, media_command, tabs: list,
                 machine: IslandStateMachine | None = None, meter=None):
        super().__init__(None, FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setProperty(theme.DARK_SURFACE_PROPERTY, True)
        self.setWindowTitle("Wisp Island")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAcceptDrops(True)
        self.voice = voice
        self.has_key = has_key
        self.media_command = media_command
        self.meter = meter
        self.machine = machine or IslandStateMachine()
        self.enabled = True
        self.monitor_mode = "primary"
        self._screen = None
        self.setFixedSize(*geometry.canvas_size())
        self.springs = SpringSet(w=ISLAND.idle[0], h=ISLAND.idle[1], split=0.0, gap=0.0,
                                 lift=0.0, vis=1.0)
        self.presentation = self.machine.presentation
        self.look = content.Look(theme.palette_for(self))
        self.look.muted = bool(voice.mic.muted)
        self._layers = [Layer(self.presentation, start=-1.0, in_ms=1.0, scale_from=1.0)]
        self._main, self._circle = self._rects()
        self._mask_key = None
        self._hover = False
        self._press: QPointF | None = None
        self._previous_foreground = 0
        self._level_source = None  # dictation / Circle to Ask level callable
        self._voice_state, self._voice_level = "idle", 0.0
        self._art_key = b""
        self._sampled: dict[str, float] = {}
        self.clock = time.monotonic  # injectable: tests and the recorder step time
        self.wall = time.time  # wall-clock time for countdowns
        self._last_tick = self.clock()
        self._screen_hooked = False

        expanded_main = self._expanded_main()
        self.panel = ExpandedPanel(voice, accent, has_key, media_command, tabs, parent=self)
        self.panel.setGeometry(expanded_main.toAlignedRect())
        self.panel.setVisible(False)
        self.panel.settings_requested.connect(self.settings_requested)
        self.panel.console_requested.connect(self.console_requested)
        for child in self.panel.findChildren(QWidget):
            if isinstance(child, EDITABLE):
                child.installEventFilter(self)
        self.shadow = ShadowLayer(self.size())

        self._frame = QTimer(self)
        self._frame.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame.timeout.connect(self._tick)
        self._hold = QTimer(self, singleShot=True, interval=ISLAND.hover_hold_ms)
        self._hold.timeout.connect(self.expand)
        self._leave = QTimer(self, singleShot=True, interval=ISLAND.collapse_delay_ms)
        self._leave.timeout.connect(self._maybe_collapse)
        self._deadline = QTimer(self, singleShot=True)
        self._deadline.timeout.connect(self.machine.update)
        self._poll = QTimer(self, interval=ISLAND.fullscreen_poll_ms)
        self._poll.timeout.connect(self._poll_environment)
        self._outside = QTimer(self, interval=50)
        self._reveal = QTimer(self, interval=ISLAND.reveal_poll_ms)  # only while slid away
        self._reveal.timeout.connect(self._poll_reveal)
        self._dwell = Dwell()
        self._outside.timeout.connect(self._check_outside_click)

        voice.visual.connect(self._on_visual)
        voice.transcript.connect(self._on_transcript)
        voice.message.connect(self._on_message)
        self.machine.subscribe(self._on_presentation)
        self.machine.subscribe_deadline(self._schedule_deadline)
        theme.signals.changed.connect(self.restyle)
        app = QGuiApplication.instance()
        app.screenAdded.connect(lambda _s: self.place())
        app.screenRemoved.connect(lambda _s: self.place())
        app.primaryScreenChanged.connect(lambda _s: self.place())
        self.restyle()
        self.place()

    # ----- appearance --------------------------------------------------------------------------
    def restyle(self, _palette=None) -> None:
        p = theme.palette_for(self)
        self.look.palette = p
        self.panel.setStyleSheet(theme.stylesheet(p) + island_stylesheet(p))
        self.panel.chat.restyle()
        for button in self.panel.findChildren(IconButton):
            button.refresh()  # icons tinted for the island's dark surface
        for chip in self.panel.findChildren(Chip):
            chip._tint()
        self.update()

    def set_accent(self, accent: str) -> None:
        self.panel.set_accent(accent)
        self.restyle()

    def update_key_prompt(self) -> None:
        self.panel.update_key_prompt()
        self.update()

    def configure(self, monitor: str, hide_when_idle: bool = True, hide_after_s: int = 6,
                  keep_for_music: bool = True) -> None:
        self.monitor_mode = monitor if monitor in ("primary", "cursor") else "primary"
        self.machine.set_autohide(hide_when_idle, hide_after_s * 1000, keep_for_music)
        self.place()

    def set_enabled(self, enabled: bool) -> None:
        """Settings → General → Show the Island."""
        self.enabled = enabled
        if enabled:
            self._poll.start()
            self._poll_environment()
        else:
            self._poll.stop()
        self._apply_visibility()

    def away_done(self) -> bool:
        """Slid away and settled: nothing left on screen."""
        return self.presentation.mode == "away" and self.springs.settled

    def _apply_visibility(self) -> None:
        """Shown unless switched off, behind a full-screen app, or slid away. While slid away
        the window is hidden, so nothing at the top of the screen is blocked, and the reveal
        zone is polled instead."""
        visible = self.enabled and self.presentation.mode != "hidden" and not self.away_done()
        if visible and not self.isVisible():
            if self.monitor_mode == "cursor":
                self.place()
            self.show()
            win.set_no_activate(int(self.winId()))
            self._sync_mask(force=True)
            self._sync_shadow()
            self._wake()
        elif not visible and self.isVisible():
            if self.machine.expanded:
                self.machine.collapse()
            self.hide()
            self.shadow.hide()
            self._frame.stop()
        watching = self.enabled and self.away_done()
        if watching and not self._reveal.isActive():
            self._dwell.reset()
            self._reveal.start()
        elif not watching:
            self._reveal.stop()

    def _poll_reveal(self) -> None:
        """~30 Hz while slid away: has the pointer rested in the top-centre zone?"""
        pos = QCursor.pos()
        screen = (QGuiApplication.screenAt(pos) if self.monitor_mode == "cursor"
                  else QGuiApplication.primaryScreen())
        inside = screen is not None and in_zone(pos, hot_zone(screen.geometry()))
        if self._dwell.update(inside, self.clock()):
            self._dwell.reset()
            self.machine.reveal()

    # ----- placement ---------------------------------------------------------------------------
    def _target_screen(self):
        if self.monitor_mode == "cursor":
            screen = QGuiApplication.screenAt(QCursor.pos())
            if screen is not None:
                return screen
        return QGuiApplication.primaryScreen()

    def place(self) -> None:
        """Top centre of the chosen monitor (below a top-docked taskbar)."""
        screen = self._target_screen()
        if screen is None:
            return
        self._screen = screen
        full, work = screen.geometry(), screen.availableGeometry()
        x = full.x() + (full.width() - self.width()) // 2
        handle = self.windowHandle()
        if handle is not None and handle.screen() is not screen:
            handle.setScreen(screen)
        self.move(x, work.y())
        self.shadow.move(x, work.y())
        self._mask_key = None
        if self.isVisible():
            self._sync_mask()

    # ----- geometry ----------------------------------------------------------------------------
    def _rects(self) -> tuple[QRectF, QRectF | None]:
        s = self.springs
        return geometry.shape_rects(self.width(), ISLAND.top, s["w"], s["h"], s["split"],
                                    s["gap"], s["lift"])

    def _expanded_main(self) -> QRectF:
        return geometry.shape_rects(self.width(), ISLAND.top, *ISLAND.expanded)[0]

    def shape_bounds(self) -> QRectF:
        main, circle = self._main, self._circle
        return main.united(circle) if circle is not None else QRectF(main)

    def _cursor_inside(self) -> bool:
        local = QPointF(self.mapFromGlobal(QCursor.pos()))
        return geometry.input_region(self._main, self._circle).contains(local.toPoint())

    def _retarget(self) -> None:
        p = self.presentation
        target = geometry.target_for(p, hover=self._hover and p.mode in COMPACT)
        animate = motion.enabled() and self.isVisible()
        self.springs.retarget(animate, w=target.width, h=target.height, split=target.split,
                              gap=target.gap, lift=target.lift, vis=target.visible)
        if not animate:
            self._main, self._circle = self._rects()
        self._wake()

    # ----- state -------------------------------------------------------------------------------
    def _on_presentation(self, p: Presentation) -> None:
        old, self.presentation = self.presentation, p
        if "hidden" in (p.mode, old.mode) or "away" in (p.mode, old.mode):
            self._apply_visibility()
        if old.content_key != p.content_key:
            self._transition(old, p)
        else:
            for layer in self._layers:
                if layer.end is None:
                    layer.p = p  # same content, newer text
        if old.mode == "expanded" and p.mode != "expanded":
            self._give_back_focus()
            self._outside.stop()
        if p.mode == "expanded" and old.mode != "expanded":
            self.panel.refresh_current()
        self._retarget()
        self.update()

    def _transition(self, old: Presentation, new: Presentation) -> None:
        now = self.clock()
        moving = motion.enabled() and self.isVisible()
        leaving_panel = old.mode == "expanded"
        snapshot = self._grab_panel() if leaving_panel and self.panel.isVisible() else None
        if leaving_panel:
            self.panel.setVisible(False)
        for layer in self._layers:
            if layer.end is None:
                layer.end = now
                layer.out_ms = ISLAND.content_out_ms if moving else 0.0
                if snapshot is not None and layer.p.mode == "expanded":
                    layer.snapshot = snapshot
        layer = Layer(new,
                      start=now + (ISLAND.content_delay_ms / 1000 if moving else 0.0),
                      in_ms=ISLAND.content_in_ms if moving else ISLAND.crossfade_ms,
                      scale_from=ISLAND.content_scale if moving else 1.0)
        if new.mode == "expanded":
            layer.snapshot = self._grab_panel()
            layer.rows = self.panel.rows()
        self._layers.append(layer)

    def _grab_panel(self) -> QPixmap:
        self.panel.ensurePolished()
        if self.panel.layout() is not None:
            self.panel.layout().activate()
        return self.panel.grab()

    def _schedule_deadline(self) -> None:
        deadline = self.machine.next_deadline()
        if deadline is None:
            self._deadline.stop()
            return
        self._deadline.start(max(0, int((deadline - self.machine.clock()) * 1000) + 5))

    # ----- reports -----------------------------------------------------------------------------
    def _on_visual(self, state: str, level: float, text: str) -> None:
        self._voice_state, self._voice_level = state, level
        self.look.orb_state = state
        self.look.muted = bool(self.voice.mic.muted)
        self.machine.set_voice(state, text)
        self._wake()

    def _on_transcript(self, role: str, text: str, final: bool, _turn: int = 0) -> None:
        if role == "model":
            self.look.reply = text
        elif role == "user" and not final:
            self.look.reply = ""

    def _on_message(self, text: str) -> None:
        """Voice notices become banners (the transcript has them too). Errors always do; other
        notices only when the conversation isn't on screen and no turn is in progress (a hint
        such as "click Talk again to send" would be stale by the time a queued banner showed)."""
        if self.voice.live_state == "error":
            self.machine.post("Voice problem", text, "error", "danger", action=self.voice.retry)
            return
        main = self.presentation.main
        if self.presentation.mode == "expanded" or (main is not None and main.tier == "voice"):
            return
        self.machine.post(text, "", "info", "accent", action=lambda: self.open_tab("Chat"))

    def show_media(self, state) -> None:
        self.panel.show_media(state)
        art = getattr(state, "art", b"") if state is not None else b""
        if art != self._art_key:
            self._art_key = art
            pixmap = QPixmap()
            self.look.art = pixmap if art and pixmap.loadFromData(art) else None
        self.machine.set_music(state)

    def set_level_source(self, source) -> None:
        """The level shown by a dictation/Circle to Ask activity (a callable, or None)."""
        self._level_source = source
        self._wake()

    def notify(self, title: str, message: str) -> None:
        icon, tone, tab = banner_style(title)
        line = message.strip().splitlines()[0] if message.strip() else ""
        action = (lambda: self.open_tab(tab)) if tab else None
        self.machine.post(title, line, icon, tone, action=action)

    # ----- user actions ------------------------------------------------------------------------
    def expand(self) -> None:
        self._hold.stop()
        if self.presentation.mode != "hidden":
            self.machine.expand()

    def collapse(self) -> None:
        self._leave.stop()
        self.machine.collapse()

    def toggle(self) -> None:
        if self.machine.expanded:
            self.collapse()
        else:
            self.expand()

    def escape(self) -> None:
        """Esc (from the keyboard hook or a key press): collapse, or dismiss a banner."""
        if self.machine.expanded:
            self.collapse()
        elif self.presentation.mode == "banner":
            self.machine.dismiss()

    def open_tab(self, name: str) -> None:
        self.panel.open_tab(name)
        self.expand()

    def _maybe_collapse(self) -> None:
        if not self.machine.expanded or self._cursor_inside():
            return
        if QApplication.activePopupWidget() is not None or QApplication.activeModalWidget():
            self._leave.start()
            return
        focus = QApplication.focusWidget()
        if (isinstance(focus, QLineEdit) and self.isAncestorOf(focus) and focus.text()
                and self.isActiveWindow()):
            self._leave.start()  # don't throw away something being typed
            return
        self.collapse()

    def _check_outside_click(self) -> None:
        """While expanded, a click anywhere outside the island collapses it (the click itself
        goes to the app underneath)."""
        if not self.machine.expanded:
            self._outside.stop()
            return
        if self._cursor_inside() or QApplication.activePopupWidget() is not None:
            return
        if win.button_down(VK_LBUTTON) or win.button_down(VK_RBUTTON):
            self.collapse()

    def _take_focus(self) -> None:
        hwnd = int(self.winId())
        current = win.foreground_hwnd()
        if current != hwnd:
            self._previous_foreground = current
            win.set_foreground(hwnd)

    def _give_back_focus(self) -> None:
        previous, self._previous_foreground = self._previous_foreground, 0
        if previous and win.foreground_hwnd() == int(self.winId()):
            win.set_foreground(previous)

    def _set_hover(self, hovered: bool) -> None:
        if hovered == self._hover:
            return
        self._hover = hovered
        self.look.hover = hovered
        self.machine.set_hover(hovered)
        self._retarget()

    # ----- Qt events ---------------------------------------------------------------------------
    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(watched, EDITABLE):
            self._take_focus()  # the one time the island takes focus: a click into a text box
        return False

    def enterEvent(self, event) -> None:
        self._leave.stop()
        self._outside.stop()
        self._set_hover(True)
        if self.presentation.mode in COMPACT:
            self._hold.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hold.stop()
        self._set_hover(False)
        if self.machine.expanded:
            self._leave.start()
            self._outside.start()
        super().leaveEvent(event)

    # ----- files dropped on the island go on the shelf (D-051) ---------------------------------
    @staticmethod
    def _local_files(event) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event) -> None:
        if not self._local_files(event):
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self._leave.stop()
        self._set_hover(True)  # no enter/leave events during a drag: hold it open ourselves
        if not self.machine.expanded:
            self.open_tab(self.drop_tab)

    def dragMoveEvent(self, event) -> None:
        if self._local_files(event):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_hover(False)
        if self.machine.expanded:
            self._leave.start()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        paths = self._local_files(event)
        if not paths:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.files_dropped.emit(paths)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if (self._press is not None and self.presentation.mode == "banner"
                and self._press.y() - event.position().y() > SWIPE_PX):
            self._press = None
            self.machine.dismiss()  # swipe up
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        press, self._press = self._press, None
        if (event.button() == Qt.MouseButton.LeftButton and press is not None
                and (event.position() - press).manhattanLength() <= SWIPE_PX):
            self._click(event.position())
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        event.accept()  # one action per double-click (the press already acted)

    def _click(self, pos: QPointF) -> None:
        p = self.presentation
        main = self._main
        self._hold.stop()
        if p.mode == "banner" and p.banner is not None:
            action = p.banner.action
            self.machine.dismiss()
            if action is not None:
                action()
        elif p.mode == "activity" and p.main is not None and p.main.kind == "music" \
                and pos.x() > main.center().x():
            self.media_command("play_pause")  # compact music: play/pause without expanding
        elif p.mode == "activity" and p.main is not None and p.main.kind == "watching" \
                and pos.x() > main.center().x():
            self.watch_stop_requested.emit()  # one click stops Watch mode
        elif (p.mode in ("idle", "activity") and pos.x() < main.left() + main.height()
              and (p.main is None or p.main.tier == "voice")):
            self.voice.toggle_talk()  # the orb: click to talk, as everywhere in Wisp
        elif p.mode in COMPACT:
            self.expand()

    def wheelEvent(self, event) -> None:
        dy = event.angleDelta().y()
        if dy < 0 and not self.machine.expanded:
            self.expand()  # scroll down
        elif dy > 0:
            if self.presentation.mode == "banner":
                self.machine.dismiss()
            elif self.machine.expanded and self.panel.header.geometry().contains(
                    event.position().toPoint()):
                self.collapse()  # scroll up on the island itself (not inside a list)
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.escape()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = self.context_menu()
        menu.exec(event.globalPos())

    def context_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction("Settings…", lambda: self.settings_requested.emit(""))
        mute = menu.addAction("Mute microphone")
        mute.setCheckable(True)
        mute.setChecked(bool(self.voice.mic.muted))
        mute.toggled.connect(self.voice.set_muted)
        menu.addAction("Open in window", self.console_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit Wisp", self.quit_requested.emit)
        return menu

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate and self.machine.expanded:
            self._leave.start()  # typed into the island, then clicked elsewhere
        return super().event(event)

    def showEvent(self, event) -> None:
        win.set_no_activate(int(self.winId()))
        handle = self.windowHandle()
        if handle is not None and not self._screen_hooked:
            handle.screenChanged.connect(self._on_screen_changed)
            self._screen_hooked = True
        self._sync_mask(force=True)
        super().showEvent(event)

    def _on_screen_changed(self, _screen) -> None:
        self._mask_key = None  # new device pixel ratio: rebuild the input region
        self._sync_mask()
        self.update()

    # ----- the frame loop ----------------------------------------------------------------------
    def _wake(self) -> None:
        if self.isVisible() and not self._frame.isActive():
            self._last_tick = self.clock()
            self._frame.start(0)

    def _tick(self) -> None:
        now = self.clock()
        dt = min(0.05, max(0.0, now - self._last_tick))
        self._last_tick = now
        before = self.shape_bounds()
        self.springs.step(dt)
        self._main, self._circle = self._rects()
        self._sample_levels(now)
        self._layers = [layer for layer in self._layers if not layer.finished(now)]
        self._expire_countdown()
        self._sync_panel(now)
        self._sync_mask()
        self._sync_shadow()
        if self.away_done():
            self._apply_visibility()  # slid out of view: hide the window
            return
        if self._hover and not self._cursor_inside() and not self.springs.settled:
            self._set_hover(False)  # the shape shrank away from under a still pointer
        dirty = before.united(self.shape_bounds()).toAlignedRect().adjusted(-3, -3, 3, 3)
        self.update(dirty)
        self._schedule(now)

    def _schedule(self, now: float) -> None:
        interval = self.frame_interval(now)
        if interval is None:
            self._frame.stop()
        elif self._frame.interval() != interval or not self._frame.isActive():
            self._frame.start(interval)

    def frame_interval(self, now: float) -> int | None:
        """How soon the next frame is needed (ms), or None: stop the timer (nothing moves)."""
        if not self.isVisible():
            return None
        if not self.springs.settled or any(
                layer.end is not None or layer.entering(now) for layer in self._layers):
            return 16
        p = self.presentation
        if p.mode == "expanded":
            return None  # the live panel paints itself
        kinds = {a.kind for a in (p.main, p.secondary) if a is not None}
        moving = motion.enabled()
        if moving and kinds & set(MOVING_KINDS):
            return 33
        if moving and "music" in kinds:
            return ISLAND.meter_frame_ms
        if "countdown" in kinds:
            return 250
        if moving and p.mode == "idle":
            return ISLAND.idle_frame_ms  # the orb's slow glow
        return None

    def _sample_levels(self, now: float) -> None:
        def due(name: str, every_ms: float) -> bool:
            if (now - self._sampled.get(name, 0.0)) * 1000 < every_ms:
                return False
            self._sampled[name] = now
            return True

        kinds = {a.kind for a in (self.presentation.main, self.presentation.secondary)
                 if a is not None}
        if "listening" in kinds and due("mic", 33):
            self.look.mic.push(min(1.0, self._voice_level * 1.6))
        if "speaking" in kinds and due("output", 33):
            self.look.output.push(min(1.0, self._voice_level * 1.6))
        if "dictation" in kinds and self._level_source is not None and due("dictation", 33):
            try:
                self.look.dictation.push(min(1.0, float(self._level_source()) * 1.6))
            except Exception:
                self._level_source = None
        if "music" in kinds and self.meter is not None and motion.enabled() \
                and due("media", ISLAND.meter_frame_ms):
            self.look.media.push(min(1.0, self.meter.peak() * 1.3))
        self.look.now, self.look.wall = now, self.wall()
        self.look.moving = motion.enabled()

    def _expire_countdown(self) -> None:
        main = self.presentation.main
        for activity in (main, self.presentation.secondary):
            if activity is not None and activity.kind == "countdown" \
                    and isinstance(activity.data, (int, float)) and activity.data <= self.wall():
                self.machine.set_countdown(None)  # due: the reminder banner takes over
                return

    def _sync_panel(self, now: float) -> None:
        """Show the live panel once the expanded shape has settled and its content is in."""
        if self.presentation.mode != "expanded":
            return
        incoming = next((layer for layer in self._layers if layer.end is None), None)
        ready = self.springs.settled and incoming is not None and not incoming.entering(now)
        if ready and not self.panel.isVisible():
            self.panel.setVisible(True)
            self.panel.raise_()

    def _sync_mask(self, force: bool = False) -> None:
        handle = self.windowHandle()
        if handle is None:
            return
        main, circle = self._main, self._circle
        key = tuple(round(v * 2) for v in (main.x(), main.y(), main.width(), main.height())) + (
            tuple(round(v * 2) for v in (circle.x(), circle.width())) if circle else ())
        if key == self._mask_key and not force:
            return
        self._mask_key = key
        handle.setMask(geometry.input_region(main, circle))

    def _sync_shadow(self) -> None:
        main = self._main
        visible = max(0.0, min(1.0, self.springs["vis"]))
        strength = max(0.0, min(1.0, (main.height() - 44) / 140)) * visible
        want = strength > 0 and self.isVisible()
        if want and not self.shadow.isVisible():
            self.shadow.move(self.pos())
            self.shadow.show()
            win.place_below(int(self.shadow.winId()), int(self.winId()))
        elif not want and self.shadow.isVisible():
            self.shadow.hide()
        self.shadow.set_shape(main, strength)

    def _poll_environment(self) -> None:
        """Once a second: hide behind full-screen apps, follow the cursor's monitor when idle."""
        try:
            hidden = fullscreen.fullscreen_over(int(self.winId()))
        except Exception as exc:
            log.info("Full-screen check failed: %s", type(exc).__name__)
            hidden = False
        if hidden != self.machine.hidden:
            self.machine.set_hidden(hidden)
        if (self.monitor_mode == "cursor" and not hidden and not self._hover
                and self.presentation.mode == "idle"):
            screen = QGuiApplication.screenAt(QCursor.pos())
            if screen is not None and screen is not self._screen:
                self.place()

    # ----- painting ----------------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.paint_island(painter, self.clock())
        painter.end()

    def paint_island(self, painter: QPainter, now: float) -> None:
        self.look.now, self.look.wall, self.look.moving = now, self.wall(), motion.enabled()
        main, circle = self._main, self._circle
        visible = max(0.0, min(1.0, self.springs["vis"]))  # fades while sliding away
        if visible <= 0.0:
            return
        radius = geometry.corner_radius(main.height())
        path = QPainterPath()
        path.addRoundedRect(main, radius, radius)
        if circle is not None:
            path.addEllipse(circle)
        painter.setOpacity(visible)
        painter.fillPath(path, QColor(0, 0, 0))
        self._paint_highlight(painter, main, radius, circle)
        painter.setOpacity(1.0)
        if self.panel.isVisible():
            return  # the live panel draws the content
        painter.save()
        painter.setClipPath(path)
        for layer in self._layers:
            alpha = layer.alpha(now)
            if alpha <= 0.01 and not layer.rows:
                continue
            painter.save()
            if layer.p.mode == "expanded":
                anchor = QPointF(main.center().x(), main.top())
            else:
                anchor = main.center()
            scale = layer.scale(now)
            if scale != 1.0:
                painter.translate(anchor)
                painter.scale(scale, scale)
                painter.translate(-anchor)
            if layer.p.mode == "expanded":
                self._paint_panel_snapshot(painter, layer, now, main, visible)
            else:
                painter.setOpacity(alpha * visible)
                height = geometry.target_for(layer.p).height
                rect = QRectF(main.left(), main.top(), main.width(), min(main.height(), height))
                content.paint_compact(painter, rect, circle, layer.p, self.look)
            painter.restore()
        painter.restore()

    def _paint_highlight(self, painter: QPainter, main: QRectF, radius: float,
                         circle: QRectF | None) -> None:
        """A very subtle 1 px inner highlight, brightest along the top edge."""
        gradient = QLinearGradient(0, main.top(), 0, main.top() + min(main.height(), 48))
        gradient.setColorAt(0.0, QColor(255, 255, 255, ISLAND.highlight_alpha))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
        pen = QPen(gradient, 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inner = main.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(inner, max(0.0, radius - 0.5), max(0.0, radius - 0.5))
        if circle is not None and circle.width() > 4:
            painter.drawEllipse(circle.adjusted(0.5, 0.5, -0.5, -0.5))

    def _paint_panel_snapshot(self, painter: QPainter, layer: Layer, now: float,
                              main: QRectF, visible: float = 1.0) -> None:
        pixmap = layer.snapshot
        if pixmap is None or pixmap.isNull():
            return
        final = self._expanded_main()
        origin = QPointF(self.panel.geometry().topLeft()) + QPointF(
            main.center().x() - final.center().x(), main.top() - final.top())
        ratio = pixmap.devicePixelRatio()
        bands = layer.rows or [QRect(0, 0, self.panel.width(), self.panel.height())]
        for index, band in enumerate(bands):
            alpha = layer.alpha(now, ISLAND.row_stagger_ms * index)
            if alpha <= 0.01:
                continue
            painter.setOpacity(alpha * visible)
            target = QRectF(band).translated(origin)
            source = QRectF(band.x() * ratio, band.y() * ratio, band.width() * ratio,
                            band.height() * ratio)
            painter.drawPixmap(target, pixmap, source)


def banner_style(title: str) -> tuple[str, str, str | None]:
    """Icon, tone and the tab a click opens, for Wisp's notifications."""
    lowered = title.lower()
    if lowered.startswith("reminder"):
        return "calendar", "warning", "Today"
    if lowered.startswith("routine done"):
        return "check", "success", "Today"
    if any(word in lowered for word in ("problem", "missed", "unavailable", "could not",
                                        "failed")):
        return "warning", "warning", None
    return "info", "accent", None
