"""Circle to Ask (F4): hold the chord, draw a loop, ask; Wisp answers aloud with a text bubble.

Press: freeze every screen (``grabWindow(0)`` before any overlay shows), show one overlay per
screen and start the spoken question. In push-to-talk mode the question streams live inside a
manual activity (activity_start … activity_end). In always-listening mode the question is
buffered (the live mic stream is paused) because server VAD would otherwise answer before the
image arrives.
Release: crop the loop's bounding box from the frozen screenshot of that screen, send it as a
realtime image frame, wait briefly (concurrent streams have no ordering guarantee), then close the
turn (activity_end, or replay the buffered audio + audio_stream_end).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QRectF, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap

from wisp.ai.gemini import NO_KEY_MESSAGE
from wisp.assist.privacy import REFUSAL, intersect
from wisp.audio.capture import MicError
from wisp.ui.overlay import CircleOverlay

log = logging.getLogger(__name__)

IMAGE_LEAD_MS = 300
BUBBLE_TIMEOUT_MS = 30000


def mask_shot(shot: QPixmap, monitor: tuple[int, int, int, int] | None,
              hidden: list[tuple[int, int, int, int]]) -> QPixmap | None:
    """Paint blocklisted windows (physical-pixel rectangles) over the frozen screenshot of one
    monitor (D-052). ``monitor`` is that monitor's physical rectangle, matched by device name;
    None when it couldn't be matched, and then None comes back if anything would need hiding,
    so nothing private is shown or sent."""
    if monitor is None:
        return None if hidden else shot
    covered = [overlap for rect in hidden if (overlap := intersect(rect, monitor))]
    if not covered:
        return shot
    width = shot.width() / shot.devicePixelRatio()  # QPainter works in logical pixels
    height = shot.height() / shot.devicePixelRatio()
    sx = width / max(1, monitor[2] - monitor[0])
    sy = height / max(1, monitor[3] - monitor[1])
    painter = QPainter(shot)
    for left, top, right, bottom in covered:
        painter.fillRect(QRectF((left - monitor[0]) * sx, (top - monitor[1]) * sy,
                                (right - left) * sx, (bottom - top) * sy), QColor(32, 32, 32))
    painter.end()
    return shot


class CircleController(QObject):
    def __init__(self, voice, live, mic, hud, bubble, has_key: Callable[[], bool],
                 accent: Callable[[], str],
                 screens: Callable[[], list] = QGuiApplication.screens,
                 overlay_factory=CircleOverlay,
                 hidden_rects: Callable[[], list] = lambda: [],
                 monitors: Callable[[], dict] = lambda: {}):
        super().__init__()
        self.voice = voice
        self.live = live
        self.mic = mic
        self.hud = hud
        self.bubble = bubble
        self.has_key = has_key
        self.accent = accent
        self.screens = screens
        self.overlay_factory = overlay_factory
        self.hidden_rects = hidden_rects  # blocklisted windows on screen (physical px)
        self.monitors = monitors  # device name -> physical rectangle
        self.overlays: list = []
        self.active = False
        self._buffered = False
        self._buffer = bytearray()
        self._answering = False
        voice.transcript.connect(self._on_transcript)
        self._bubble_timeout = QTimer(self)
        self._bubble_timeout.setSingleShot(True)
        self._bubble_timeout.timeout.connect(self._stop_answering)

    def on_hotkey(self, name: str, kind: str) -> None:
        if name != "circle":
            return
        if kind == "press":
            self.begin()
        elif kind == "release":
            self.finish()
        elif kind == "cancel":
            self.cancel()

    # ----- gesture -----------------------------------------------------------------------------
    def begin(self) -> None:
        if self.active:
            return
        if not self.has_key():
            self.hud.flash(NO_KEY_MESSAGE, 4000, "muted")
            return
        hidden = self.hidden_rects()
        monitors = self.monitors() if hidden else {}
        shots = [(screen, mask_shot(screen.grabWindow(0),
                                    monitors.get(screen.name()) if hidden else None, hidden))
                 for screen in self.screens()]
        if any(shot is None for _screen, shot in shots):
            self.hud.flash(REFUSAL + " A private window is on screen.", 4000, "muted")
            return
        try:
            self.mic.acquire("circle")
        except MicError as exc:
            self.hud.flash(str(exc), 4000, "danger")
            return
        accent = self.accent()
        self.overlays = [self.overlay_factory(screen, shot, accent) for screen, shot in shots]
        for overlay in self.overlays:
            overlay.show()
            overlay.raise_()
        self._buffered = self.voice.always_listening
        self._buffer = bytearray()
        if self._buffered:
            self.voice.suspend_always(True)
            self.mic.subscribe("circle", self._buffer.extend)
        else:
            self.live.begin_turn()
            self.mic.subscribe("circle", self.live.push_audio)
        self.voice.talking = True
        self.active = True
        self.hud.show_state("Circle it and ask your question", "accent",
                            lambda: self.mic.level)

    def _end_capture(self) -> None:
        self.active = False
        self.voice.talking = False
        self.mic.unsubscribe("circle")
        self.mic.release("circle")
        for overlay in self.overlays:
            overlay.hide()
            overlay.deleteLater()

    def cancel(self) -> None:
        if not self.active:
            return
        self._end_capture()
        self.overlays = []
        if self._buffered:
            self.voice.suspend_always(False)
        else:
            self.live.cancel_turn()
        self.hud.hide_now()

    def finish(self) -> None:
        if not self.active:
            return
        drawn = [o for o in self.overlays if o.has_stroke()]
        crop = drawn[0].crop() if drawn else None
        self._end_capture()
        self.overlays = []
        if crop is None:
            if self._buffered:
                self.voice.suspend_always(False)
            else:
                self.live.cancel_turn()
            self.hud.flash("Nothing was circled", 1500, "muted")
            return
        jpeg, anchor = crop
        self.live.send_image(jpeg)
        self.voice.awaiting_reply = True
        self.hud.flash("Looking…", 1500)
        self._answering = True
        self.bubble.show_at(anchor, "…")
        self._bubble_timeout.start(BUBBLE_TIMEOUT_MS)
        audio = bytes(self._buffer)
        QTimer.singleShot(IMAGE_LEAD_MS, lambda: self._close_turn(audio))

    def _close_turn(self, audio: bytes) -> None:
        if self._buffered:
            for start in range(0, len(audio), 1024):
                self.live.push_audio(audio[start:start + 1024])
            self.live.audio_stream_end()
            self.voice.suspend_always(False)
        else:
            self.live.end_turn()

    # ----- answer bubble -----------------------------------------------------------------------
    def _on_transcript(self, role: str, text: str, final: bool, _turn: int = 0) -> None:
        if not self._answering or role != "model":
            return
        self.bubble.set_text(text)
        if final:
            self._stop_answering(12.0)

    def _stop_answering(self, linger: float = 0.0) -> None:
        self._answering = False
        self._bubble_timeout.stop()
        self.bubble.finish(linger)
