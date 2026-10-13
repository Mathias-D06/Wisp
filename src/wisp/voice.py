"""Voice controller: push-to-talk, orb clicks, always-listening, console text, mic mute.

Lives on the Qt thread. It routes microphone chunks to the Live session, keeps the orb's
visual state current and turns Live session events into UI signals.
"""

from __future__ import annotations

import contextlib
import logging
import time

from PySide6.QtCore import QObject, QTimer, Signal

from wisp.ai.gemini import NO_KEY_MESSAGE
from wisp.audio.capture import MicCapture, MicError
from wisp.audio.playback import Player
from wisp.live.session import LiveCallbacks, LiveState

log = logging.getLogger(__name__)

WAKE_LEVEL = 0.08


class VoiceSignals(QObject):
    """Thread-safe bridge: emitted from the core loop, delivered on the Qt thread."""

    state = Signal(str, str)
    user_text = Signal(int, str, bool)  # turn number, text so far, final
    model_text = Signal(str, bool)
    tool = Signal(str, str)
    turn_done = Signal()
    hint = Signal(str)


DROPPED_MESSAGES = {
    "short": "That was too short to send. Hold the talk key or the Talk button while you speak, "
             "or click Talk once to start and again to send.",
    "silent": "Wisp didn't hear any speech, so nothing was sent. Check that your microphone isn't "
              "muted, then try Settings → Hotkeys and audio → Test microphone.",
}
PREROLL_MS = 300  # audio from just before push-to-talk activated (the keys' hold time)
CLICK_MS = 350  # a Talk press shorter than this is a click: keep listening until clicked again
ORB_DEBOUNCE_MS = 400


def make_callbacks(signals: VoiceSignals, player: Player, on_user_final) -> LiveCallbacks:
    return LiveCallbacks(
        state=lambda state, detail: signals.state.emit(state.value, detail),
        user_text=lambda turn, text, final: signals.user_text.emit(turn, text, final),
        user_final=on_user_final,
        model_text=lambda text, final: signals.model_text.emit(text, final),
        model_audio=player.feed,
        interrupted=player.clear,
        turn_complete=signals.turn_done.emit,
        tool_activity=lambda name, status: signals.tool.emit(name, status),
        turn_dropped=lambda reason: signals.hint.emit(DROPPED_MESSAGES[reason]),
    )


class VoiceController(QObject):
    visual = Signal(str, float, str)  # orb state, level, status text
    transcript = Signal(str, str, bool, int)  # role (user/model/notice), text, final, turn
    message = Signal(str)  # short user-facing notice (errors, hints)

    def __init__(self, live, mic: MicCapture, player: Player, signals: VoiceSignals,
                 settings_store, confirmations, notify):
        super().__init__()
        self.live = live
        self.mic = mic
        self.player = player
        self.settings_store = settings_store
        self.confirmations = confirmations
        self.notify = notify
        self.talking = False
        self.awaiting_reply = False
        self.tools_running = 0
        self.live_state = LiveState.IDLE.value
        self.live_detail = ""
        self.always_listening = settings_store.get().audio.always_listening
        self._always_suspended = False
        settings_store.subscribe(self._on_settings)
        signals.state.connect(self._on_state)
        signals.user_text.connect(
            lambda turn, text, final: self.transcript.emit("user", text, final, turn))
        self._talk_pressed_at = 0.0
        self._talk_toggle = False  # Talk was clicked (not held): listening until clicked again
        self._talk_consumed = False
        self._orb_at = 0.0
        signals.model_text.connect(self._on_model_text)
        signals.tool.connect(self._on_tool)
        signals.turn_done.connect(self._on_turn_done)
        signals.hint.connect(self._tell)
        self._last_visual: tuple[str, float, str] | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_visual)
        self._timer.start(66)
        if self.always_listening:
            QTimer.singleShot(0, lambda: self._start_always_listening())

    def _on_settings(self, settings) -> None:
        """Settings are saved on the Qt thread (tray, console, Settings window)."""
        enabled = settings.audio.always_listening
        if enabled == self.always_listening:
            return
        self.always_listening = enabled
        self.live.request_reconnect()  # VAD mode is part of the session setup
        if enabled:
            self._start_always_listening()
        else:
            self.mic.unsubscribe("always")
            self.mic.release("always")

    # ----- push-to-talk / orb ------------------------------------------------------------------
    def ptt_press(self, preroll: bool = False) -> None:
        if self.talking:
            return
        if self.live_state == LiveState.NO_KEY.value or not self.live.has_key():
            self.live.connect()
            self._tell(NO_KEY_MESSAGE)
            return
        try:
            self.mic.acquire("voice")
        except MicError as exc:
            self._tell(str(exc))
            return
        self.talking = True
        self.awaiting_reply = False
        self.player.clear()
        self.live.begin_turn()
        if preroll:
            # Words spoken while the keys were still arming (hold time) are sent too.
            recent = self.mic.preroll(PREROLL_MS)
            if recent:
                self.live.push_audio(recent)
        self.mic.subscribe("voice", self.live.push_audio)
        self.mic.release("ptt-arm")

    def ptt_release(self) -> None:
        self._talk_toggle = False
        self.mic.release("ptt-arm")
        if not self.talking:
            return
        self.talking = False
        self.mic.unsubscribe("voice")
        self.mic.release("voice")
        self.live.end_turn()
        self.awaiting_reply = True

    def ptt_cancel(self) -> None:
        self._talk_toggle = False
        self.mic.release("ptt-arm")
        if not self.talking:
            return
        self.talking = False
        self.mic.unsubscribe("voice")
        self.mic.release("voice")
        self.live.cancel_turn()

    def toggle_talk(self) -> None:
        """Orb click: start talking, or stop and send; clicking while it speaks interrupts.
        A second click within ORB_DEBOUNCE_MS (a double-click) is ignored."""
        now = time.monotonic()
        if (now - self._orb_at) * 1000 < ORB_DEBOUNCE_MS:
            return
        self._orb_at = now
        if self.talking:
            self.ptt_release()
        else:
            self.ptt_press()

    def talk_pressed(self) -> None:
        """Console Talk button: hold to talk, or click to start and click again to send."""
        if self.talking and self._talk_toggle:
            self._talk_toggle = False
            self._talk_consumed = True
            self.ptt_release()
            return
        self._talk_consumed = False
        self._talk_pressed_at = time.monotonic()
        self.ptt_press()

    def talk_released(self) -> None:
        if self._talk_consumed or not self.talking:
            self._talk_consumed = False
            return
        if (time.monotonic() - self._talk_pressed_at) * 1000 < CLICK_MS:
            self._talk_toggle = True
            self._tell("Listening — click Talk again to send.")
            return
        self.ptt_release()

    def retry(self) -> None:
        """Try the voice connection again after an error."""
        self._tell("Reconnecting to Gemini…")
        self.live.connect()

    def on_hotkey(self, name: str, kind: str) -> None:
        if name != "push_to_talk":
            return
        if kind == "arm":
            # Keys are down but not yet held long enough: open the mic so the pre-roll holds
            # the first words. Nothing is sent unless "press" follows.
            if not self.talking and not self.mic.muted and self.live.has_key():
                with contextlib.suppress(MicError):  # "press" reports the problem
                    self.mic.acquire("ptt-arm")
        elif kind == "disarm":
            self.mic.release("ptt-arm")
        elif kind == "press":
            self.ptt_press(preroll=True)
        elif kind == "release":
            self.ptt_release()
        elif kind == "cancel":
            self.ptt_cancel()

    # ----- text, mute, always-listening --------------------------------------------------------
    def send_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if not self.live.has_key():
            self._tell(NO_KEY_MESSAGE)
            return
        self.transcript.emit("user", text, True, 0)
        self.confirmations.on_user_utterance(text)
        self.player.clear()
        self.live.send_text(text)
        self.awaiting_reply = True

    def set_muted(self, muted: bool) -> None:
        if muted and self.talking:
            self.ptt_cancel()
        self.mic.set_muted(muted)
        self.settings_store.update(lambda s: setattr(s.audio, "mic_muted", muted))
        if muted and self.always_listening:
            self.live.audio_stream_end()
        self._tell("Microphone muted." if muted else "Microphone on.")

    def set_always_listening(self, enabled: bool) -> None:
        self.settings_store.update(lambda s: setattr(s.audio, "always_listening", enabled))

    def _start_always_listening(self) -> None:
        if not self.live.has_key():
            self._tell(NO_KEY_MESSAGE)
            return
        try:
            self.mic.acquire("always")
        except MicError as exc:
            self._tell(str(exc))
            return
        self.mic.subscribe("always", self._always_chunk)
        self.live.connect()

    def suspend_always(self, suspended: bool) -> None:
        """Pause always-listening streaming (Circle to Ask buffers its question instead)."""
        self._always_suspended = suspended

    def _always_chunk(self, chunk: bytes) -> None:
        # Called on the mic thread. Wake an idle session when the user starts speaking.
        if self._always_suspended:
            return
        if self.live.state == LiveState.IDLE and self.mic.level > WAKE_LEVEL:
            self.live.connect()
            self.live.push_audio(self.mic.preroll())
            return
        self.live.push_audio(chunk)

    def apply_settings(self) -> None:
        self.mic.reopen()
        self.player.reopen()

    # ----- live events -------------------------------------------------------------------------
    def _on_state(self, state: str, detail: str) -> None:
        self.live_state, self.live_detail = state, detail
        if state in (LiveState.ERROR.value, LiveState.NO_KEY.value):
            self.awaiting_reply = False
            self._tell(detail)

    def _on_model_text(self, text: str, final: bool) -> None:
        self.awaiting_reply = False
        self.transcript.emit("model", text, final, 0)

    def _on_tool(self, name: str, status: str) -> None:
        self.tools_running += 1 if status == "start" else -1
        self.tools_running = max(0, self.tools_running)

    def _on_turn_done(self) -> None:
        self.awaiting_reply = False

    def _tell(self, text: str) -> None:
        log.info("Voice notice: %s", text)
        self.message.emit(text)
        self.transcript.emit("notice", text, True, 0)

    def _refresh_visual(self) -> None:
        """Emit only on a real change: an idle Wisp then costs no repaints (D-044)."""
        state, level, text = self.compute_visual()
        last = self._last_visual
        same = last is not None and last[0] == state and last[2] == text
        if same and abs(last[1] - level) < 0.02:
            return
        self._last_visual = (state, level, text)
        self.visual.emit(state, level, text)

    def compute_visual(self) -> tuple[str, float, str]:
        live = self.live_state
        if live == LiveState.NO_KEY.value:
            return "offline", 0.0, "Add your API key"
        if live == LiveState.ERROR.value:
            return "error", 0.0, self.live_detail or "Error"
        if live == LiveState.OFFLINE.value:
            return "offline", 0.0, self.live_detail or "Offline"
        if self.mic.muted and not self.player.is_playing():
            return "idle", 0.0, "Mic muted"
        if self.talking:
            return "listening", self.mic.level, "Listening…"
        if self.player.is_playing():
            return "speaking", self.player.level, "Speaking"
        if self.tools_running:
            return "thinking", 0.0, "Working…"
        if self.awaiting_reply:
            return "thinking", 0.0, "Thinking…"
        if live in (LiveState.CONNECTING.value, LiveState.RECONNECTING.value):
            return "thinking", 0.0, self.live_detail
        if self.always_listening and live == LiveState.READY.value:
            return "listening", self.mic.level, "Listening"
        return "idle", 0.0, "Ready"
