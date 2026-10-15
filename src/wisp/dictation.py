"""Dictation (F3): hold the chord to record, release to paste clean text where the caret is.

Flow: chord press → record mic (16 kHz) → chord release → Gemini cleans the speech
(ai/dictation.py) → wait until modifier keys are up → save the clipboard → put the text on the
clipboard (excluded from clipboard history) → Ctrl+V into the original window → restore the
previous clipboard 0.6 s later, unless something else changed it meanwhile.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from wisp.ai.dictation import word_count
from wisp.ai.gemini import NO_KEY_MESSAGE, describe_error
from wisp.audio.capture import MicError
from wisp.audio.convert import has_speech

log = logging.getLogger(__name__)

MIN_SECONDS = 0.35
MAX_SECONDS = 300
RESTORE_DELAY_MS = 600
MODIFIER_WAIT_MS = 1500
BYTES_PER_SECOND = 32000  # 16 kHz * 2 bytes


SILENT_MESSAGE = "Didn't hear any speech — check your microphone (Settings → Hotkeys and audio)."


@dataclass
class DictationDeps:
    """Windows/Gemini side effects, injectable for tests."""

    transcribe: Callable[[bytes], str]
    has_key: Callable[[], bool]
    snapshot: Callable[[], Any]
    set_text: Callable[[str], None]
    restore: Callable[[Any], None]
    clipboard_sequence: Callable[[], int]
    paste: Callable[[], None]
    modifiers_down: Callable[[], bool]
    foreground: Callable[[], Any]
    activate: Callable[[int], bool]
    target_is_elevated: Callable[[Any], bool]
    save_debug: Callable[[bytes], None] = lambda pcm: None
    extra: dict = field(default_factory=dict)


def insert_text(deps: DictationDeps, target, text: str) -> str:
    """Paste ``text`` into ``target`` (a WindowInfo, or None for the window in front) and put the
    previous clipboard back afterwards, unless something else changed it meanwhile. Returns
    "pasted", or "copied" when the target is an administrator window (Windows blocks automatic
    paste there, D-025). Also used by Screen Assist's Insert (D-052). Never presses Enter."""
    if target is not None and deps.target_is_elevated(target):
        deps.set_text(text)
        return "copied"
    try:
        saved = deps.snapshot()
    except Exception as exc:
        log.warning("Clipboard snapshot failed: %s", exc)
        saved = None
    deps.set_text(text)
    ours = deps.clipboard_sequence()
    current = deps.foreground()
    if target is not None and (current is None or current.hwnd != target.hwnd):
        deps.activate(target.hwnd)
    deps.paste()

    def restore() -> None:
        if saved is None:
            return
        if deps.clipboard_sequence() != ours:
            log.info("Clipboard changed after paste; not restoring")
            return
        try:
            deps.restore(saved)
        except Exception as exc:
            log.warning("Clipboard restore failed: %s", exc)

    QTimer.singleShot(RESTORE_DELAY_MS, restore)
    return "pasted"


class DictationController(QObject):
    _transcribed = Signal(int, str, str, float)  # token, text, error, seconds
    state = Signal(str)  # "recording" | "transcribing" | "pasted" | "idle" | "error"

    def __init__(self, deps: DictationDeps, mic, hud, stats, notify):
        super().__init__()
        self.deps = deps
        self.mic = mic
        self.hud = hud
        self.stats = stats
        self.notify = notify
        self.recording = False
        self._buffer = bytearray()
        self._started = 0.0
        self._target = None
        self._token = 0
        self.last_text = ""
        self._transcribed.connect(self._on_transcribed)
        self._limit = QTimer(self)
        self._limit.setSingleShot(True)
        self._limit.timeout.connect(self.stop)

    def on_hotkey(self, name: str, kind: str) -> None:
        if name != "dictation":
            return
        if kind == "press":
            self.start()
        elif kind == "release":
            self.stop()
        elif kind == "cancel":
            self.cancel()

    def start(self) -> None:
        if self.recording:
            return
        if not self.deps.has_key():
            self.hud.flash(NO_KEY_MESSAGE, 4000, "muted")
            self.notify("Dictation needs an API key", NO_KEY_MESSAGE)
            return
        try:
            self.mic.acquire("dictation")
        except MicError as exc:
            self.hud.flash(str(exc), 4000, "danger")
            return
        self._target = self.deps.foreground()
        self._buffer = bytearray()
        self.mic.subscribe("dictation", self._buffer.extend)
        self._started = time.monotonic()
        self.recording = True
        self._limit.start(MAX_SECONDS * 1000)
        self.hud.show_state("Dictating… release to insert", "success", lambda: self.mic.level)
        self.state.emit("recording")

    def _stop_recording(self) -> bytes:
        self.recording = False
        self._limit.stop()
        self.mic.unsubscribe("dictation")
        self.mic.release("dictation")
        return bytes(self._buffer)

    def cancel(self) -> None:
        if self.recording:
            self._stop_recording()
            self.hud.hide_now()
            self.state.emit("idle")

    def stop(self) -> None:
        if not self.recording:
            return
        audio = self._stop_recording()
        seconds = len(audio) / BYTES_PER_SECOND
        if seconds < MIN_SECONDS:
            self.hud.hide_now()
            self.state.emit("idle")
            return
        if not has_speech(audio):
            # Silence makes the model invent text; never paste that (D-039).
            self.hud.flash(SILENT_MESSAGE, 3500, "muted")
            self.state.emit("idle")
            return
        self.deps.save_debug(audio)
        self._token += 1
        token = self._token
        self.hud.show_state("Transcribing…", "warning")
        self.state.emit("transcribing")

        def work() -> None:
            try:
                text = self.deps.transcribe(audio)
                self._transcribed.emit(token, text, "", seconds)
            except Exception as exc:
                log.warning("Dictation failed: %s", type(exc).__name__)
                self._transcribed.emit(token, "", describe_error(exc), seconds)

        threading.Thread(target=work, name="dictation", daemon=True).start()

    def _on_transcribed(self, token: int, text: str, error: str, seconds: float) -> None:
        if token != self._token:
            return
        if error:
            self.hud.flash(error, 4000, "danger")
            self.state.emit("error")
            return
        if not text.strip():
            self.hud.flash("No speech heard", 1800, "muted")
            self.state.emit("idle")
            return
        self.last_text = text
        self._wait_for_keys(text, seconds, time.monotonic())

    def _wait_for_keys(self, text: str, seconds: float, since: float) -> None:
        """Pasting while Win is still held would turn Ctrl+V into Win+V (clipboard history)."""
        waited_ms = (time.monotonic() - since) * 1000
        if self.deps.modifiers_down() and waited_ms < MODIFIER_WAIT_MS:
            QTimer.singleShot(30, lambda: self._wait_for_keys(text, seconds, since))
            return
        self._paste(text, seconds)

    def _paste(self, text: str, seconds: float) -> None:
        if insert_text(self.deps, self._target, text) == "copied":
            self.hud.flash("Copied — press Ctrl+V (admin windows block automatic paste)", 4500)
        else:
            self.hud.flash(f"Inserted {word_count(text)} words", 1500, "success")
        self._record(text, seconds)
        self.state.emit("pasted")

    def _record(self, text: str, seconds: float) -> None:
        if self.stats is not None:
            self.stats.record("dictation", words=word_count(text), seconds=seconds)
