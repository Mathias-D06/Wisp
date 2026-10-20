"""Screen Assist in the app (D-052): the hotkey, answers on the Qt thread, reading them aloud,
inserting a drafted reply, and Watch mode's timer.

Hotkey (hold Ctrl+Alt+Space by default)
  The press captures the window in front straight away, before Wisp shows anything, and starts
  listening. Speak the question while holding; release to ask. A tap without speech asks the
  default question (explain, and point out what looks wrong or worth acting on). A hold during
  which the microphone delivered only silence asks nothing and says which Windows setting to
  check (D-055). Pressing again within the conversation is a follow-up: the screenshot is
  reused unless the window changed.

  The microphone opens on a thread ("assist-mic"), so the press never waits for it (opening it
  the first time can take more than a second, D-058). Whether the keys were tapped or held is
  timed from the key events, not from how much audio arrived. Every press ends in an answer, an
  error, or "I didn't hear a question", and the log says which.

Requests run on threads; results come back through signals. Answers are read aloud with Gemini
TTS in the voice from Settings → Loadout when ``speak_answers`` allows it (code blocks are not
read; long answers stop at the first part and say the rest is on screen). Questions asked
through the voice session are spoken by that session instead.

Reply mode drafts text; "Insert" pastes it into the window the screenshot came from, after a
click, and nothing is ever sent (no Enter is pressed).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from wisp.ai.gemini import describe_error
from wisp.assist import prompts
from wisp.assist.engine import AssistEngine, Blocked, CaptureError, Exchange, Shot, WatchCheck

log = logging.getLogger(__name__)

MIN_QUESTION_S = 0.4  # keys held at least this long: a question by voice, not a tap
MIN_AUDIO_S = 0.3  # less audio than this from a hold: the microphone was still starting
SHOT_TIMEOUT_S = 10
NO_QUESTION = "I didn't hear a question."
BYTES_PER_SECOND = 32000
SPEAK_LIMIT = 700


def speech_text(answer: str, limit: int = SPEAK_LIMIT) -> str:
    """What to read aloud: no code, no markdown marks, at most ``limit`` characters (cut at a
    sentence) with a pointer to the rest."""
    text = re.sub(r"```.*?(```|$)", " (the code is on screen) ", answer, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s{0,3}(#+|[-*•]|\d+[.)])\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: end + 1] if end > limit // 3 else cut.rstrip() + "…") + \
        " The rest is on screen."


class ScreenAssist(QObject):
    answered = Signal(object)  # Exchange
    failed = Signal(str)
    unheard = Signal(str)  # the keys were held, but no question came through (D-058)
    progress = Signal(str)  # while a question waits, e.g. "Google is busy, retrying… (2 of 3)"
    busy_changed = Signal(bool)
    started = Signal()  # a question is on its way (the card may open)
    speaking_changed = Signal(bool)
    _done = Signal(int, object, str, bool)  # token, exchange, error, speak
    _spoken = Signal(int, object)  # token, Speech or None
    _invoke = Signal(object)
    _mic_opened = Signal(int, str, str)  # press, mic user, error ("" when open)
    _busy_note = Signal(int, str)  # token, note

    def __init__(self, engine: AssistEngine, mic, player, settings, has_key: Callable[[], bool],
                 voice_name: Callable[[], str], speak_allowed: Callable[[], bool],
                 paste: Callable[[int, str], str], to_wav: Callable[[bytes], bytes],
                 has_speech: Callable[[bytes], bool], resample: Callable[[bytes, int], bytes],
                 on_speech_usage: Callable[[object], None] = lambda speech: None,
                 mic_silence: Callable[[bytes], str | None] = lambda pcm: None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__()
        self.engine = engine
        self.mic = mic
        self.player = player
        self.settings = settings  # () -> Settings
        self.has_key = has_key
        self.voice_name = voice_name
        self.speak_allowed = speak_allowed
        self.paste = paste
        self.to_wav = to_wav
        self.has_speech = has_speech
        self.resample = resample
        self.on_speech_usage = on_speech_usage
        self.mic_silence = mic_silence  # the notice if the mic delivered only silence (D-055)
        self.clock = clock
        self.busy = False
        self.listening = False
        self.last: Exchange | None = None
        self._buffer = bytearray()
        self._press_shot: Future | None = None
        self._press = 0  # numbers presses, so a mic that opens after its release is let go
        self._pressed_at = 0.0
        self._mic_user = ""
        self._mic_error: str | None = None  # None: still opening; "": open; else why not
        self._token = 0
        self._asked_at = 0.0
        self._speech_token = 0
        self.speaking = False
        self._done.connect(self._finished)
        self._spoken.connect(self._play)
        self._invoke.connect(lambda fn: fn(), Qt.ConnectionType.QueuedConnection)
        self._mic_opened.connect(self._on_mic_opened)
        self._busy_note.connect(self._on_busy_note)

    # ----- the hotkey ----------------------------------------------------------------------------
    def on_hotkey(self, name: str, kind: str) -> None:
        if name != "screen_assist":
            return
        if kind == "press":
            self.press()
        elif kind == "release":
            self.release()
        elif kind == "cancel":
            self.cancel()

    def press(self) -> None:
        if self.busy or self.listening:
            log.info("Screen Assist hotkey ignored: %s",
                     "a question is still running" if self.busy else "already listening")
            return
        if not self.has_key():
            log.info("Screen Assist hotkey: no API key")
            self.failed.emit("Screen Assist needs your Gemini API key (Settings → General).")
            return
        target = self.settings().screen_assist.capture
        future: Future = Future()
        follow = self.engine.active()
        preferred = self.engine.conversation.shot.hwnd if follow else None

        def grab() -> None:
            try:
                future.set_result(self.engine.capturer.capture(
                    target, "screen_assist", "hotkey", preferred_hwnd=preferred))
            except (Blocked, CaptureError) as exc:  # expected: the card says why
                log.info("Screen Assist capture skipped: %s", exc)
                future.set_exception(exc)
            except Exception as exc:
                log.exception("Screen Assist capture failed")
                future.set_exception(exc)

        threading.Thread(target=grab, name="assist-capture", daemon=True).start()
        self._press += 1
        self._press_shot = future
        self._pressed_at = self.clock()
        self._buffer = bytearray()
        self._mic_user, self._mic_error = f"assist-{self._press}", None
        self.mic.subscribe(self._mic_user, self._buffer.extend)  # audio flows once it's open
        self.listening = True
        self.started.emit()  # "Listening… release to ask" at once, not after the mic opens
        threading.Thread(target=self._open_mic, args=(self._press, self._mic_user),
                         name="assist-mic", daemon=True).start()

    def _open_mic(self, press: int, user: str) -> None:
        started = time.monotonic()
        try:
            self.mic.acquire(user)
            error = ""
        except Exception as exc:  # no microphone: a tap still works
            error = str(exc) or type(exc).__name__
        log.info("Screen Assist: microphone %s after %.2f s",
                 f"unavailable ({error})" if error else "open", time.monotonic() - started)
        self._mic_opened.emit(press, user, error)

    def _on_mic_opened(self, press: int, user: str, error: str) -> None:
        if press != self._press or not self.listening:  # released before the mic was ready
            if not error:
                self.mic.release(user)
            return
        self._mic_error = error

    def _stop_listening(self) -> bytes:
        if not self.listening:
            return b""
        self.listening = False
        self.mic.unsubscribe(self._mic_user)
        if self._mic_error == "":  # open; one still opening is let go in _on_mic_opened
            self.mic.release(self._mic_user)
        return bytes(self._buffer)

    def release(self) -> None:
        future, self._press_shot = self._press_shot, None
        if future is None:
            log.info("Screen Assist hotkey release ignored (no press waiting)")
            return
        held = self.clock() - self._pressed_at
        mic = self._mic_error
        audio = self._stop_listening()
        outcome, message = self._outcome(held, audio, mic)
        log.info("Screen Assist hotkey: held %.2f s, %.2f s of audio, microphone %s → %s",
                 held, len(audio) / BYTES_PER_SECOND,
                 "still opening" if mic is None else ("open" if mic == "" else "unavailable"),
                 outcome)
        if outcome == "question":
            self.ask(audio_wav=self.to_wav(audio), shot_future=future, origin="hotkey")
        elif outcome == "quick look":
            self.ask(shot_future=future, origin="hotkey")
        elif outcome == "silent microphone":
            self.failed.emit(message)
        else:
            self.unheard.emit(message)

    def _outcome(self, held: float, audio: bytes, mic: str | None) -> tuple[str, str]:
        """What a hotkey press becomes: (outcome, message for the card)."""
        if held < MIN_QUESTION_S:
            return "quick look", ""
        if mic:
            return "no question (no microphone)", f"{NO_QUESTION} {mic}"
        notice = self.mic_silence(audio)
        if notice:
            return "silent microphone", notice
        if self.has_speech(audio):
            return "question", ""
        if len(audio) / BYTES_PER_SECOND < MIN_AUDIO_S:
            return "no question (microphone still starting)", (
                f"{NO_QUESTION} The microphone was still starting: hold the keys a moment "
                "before you speak, or tap them for a quick look.")
        return "no question (no speech)", (
            f"{NO_QUESTION} Hold the keys while you speak, or tap them for a quick look.")

    def cancel(self) -> None:
        if self._press_shot is not None:
            log.info("Screen Assist hotkey cancelled (another key was pressed)")
        self._press_shot = None
        self._stop_listening()

    # ----- asking ---------------------------------------------------------------------------------
    def ask(self, question: str | None = None, mode: str | None = None,
            target: str | None = None, new: bool = False, detailed: bool = False,
            audio_wav: bytes = b"", shot_future: Future | None = None,
            origin: str = "island", speak: bool = True) -> bool:
        """Ask on a thread; ``answered`` or ``failed`` follows. False if a question is running."""
        if self.busy:
            log.info("Screen Assist question not asked: another one is running")
            return False
        self.busy = True
        self._token += 1
        token = self._token
        self._asked_at = self.clock()
        log.info("Screen Assist asks %s (%s, from %s)", self.engine.model.model_name(),
                 "spoken question" if audio_wav else ("typed question" if question
                                                      else "quick look"), origin)
        self.busy_changed.emit(True)
        self.started.emit()

        def work() -> None:
            try:
                shot: Shot | None = None
                if shot_future is not None:
                    try:
                        shot = shot_future.result(SHOT_TIMEOUT_S)
                    except FutureTimeout:
                        raise CaptureError("The screenshot took too long. Try again.") from None
                exchange = self.engine.ask(
                    question, mode, target, audio_wav, new, detailed, origin, shot=shot,
                    on_busy=lambda note: self._busy_note.emit(token, note))
                self._done.emit(token, exchange, "", speak)
            except (Blocked, CaptureError) as exc:
                self._done.emit(token, None, str(exc), False)
            except Exception as exc:
                log.exception("Screen Assist failed")
                self._done.emit(token, None, describe_error(exc, self.engine.model.model_name()),
                                False)

        threading.Thread(target=work, name="screen-assist", daemon=True).start()
        return True

    def ask_blocking(self, question: str | None, mode: str | None, target: str | None,
                     timeout: float = 180.0) -> Exchange:
        """For the voice session's tool (a worker thread): answer, show it on the card, and
        return it. The voice session speaks it, so Gemini TTS doesn't."""
        done: Future = Future()

        def on_answer(exchange) -> None:
            if not done.done():
                done.set_result(exchange)

        def on_failure(message) -> None:
            if not done.done():
                done.set_exception(RuntimeError(message))

        self.answered.connect(on_answer)
        self.failed.connect(on_failure)
        try:
            self._call_on_ui(lambda: self.ask(question, mode, target, origin="voice",
                                              speak=False)
                             or on_failure("Screen Assist is busy with another question."))
            return done.result(timeout)
        finally:
            self.answered.disconnect(on_answer)
            self.failed.disconnect(on_failure)

    def _call_on_ui(self, fn: Callable[[], object]) -> None:
        self._invoke.emit(fn)  # queued: runs on the Qt thread

    def more(self) -> bool:
        return self.ask(prompts.MORE, detailed=True)

    def _on_busy_note(self, token: int, note: str) -> None:
        if token == self._token and self.busy:
            self.progress.emit(note)

    def _finished(self, token: int, exchange: Exchange | None, error: str, speak: bool) -> None:
        if token != self._token:
            return
        self.busy = False
        self.busy_changed.emit(False)
        elapsed = self.clock() - self._asked_at
        if exchange is None:
            log.info("Screen Assist ended with an error after %.1f s: %s", elapsed, error)
            self.failed.emit(error)
            return
        reply = exchange.reply
        log.info("Screen Assist answered in %.1f s by %s%s", elapsed,
                 (reply.model if reply is not None and reply.model else "the model"),
                 f" (standing in for {reply.fallback_from})"
                 if reply is not None and reply.fallback_from else "")
        self.last = exchange
        self.answered.emit(exchange)
        if speak and self.speak_allowed():
            self.speak(exchange.answer)

    # ----- reading aloud --------------------------------------------------------------------------
    def speak(self, text: str) -> None:
        words = speech_text(text)
        if not words:
            return
        self._speech_token += 1
        token = self._speech_token
        self.speaking = True
        self.speaking_changed.emit(True)
        voice = self.voice_name()

        def work() -> None:
            try:
                self._spoken.emit(token, self.engine.model.speak(words, voice))
            except Exception:
                log.exception("Reading the answer aloud failed")
                self._spoken.emit(token, None)

        threading.Thread(target=work, name="assist-speech", daemon=True).start()

    def _play(self, token: int, speech) -> None:
        if token != self._speech_token or not self.speaking:
            return
        if speech is not None and speech.pcm:
            self.on_speech_usage(speech)
            # speak() runs only when reading aloud is allowed or was asked for ("Speak it")
            self.player.feed(self.resample(speech.pcm, speech.rate), force=True)
            QTimer.singleShot(250, self._watch_playback)
        else:
            self._stop_speaking_state()

    def _watch_playback(self) -> None:
        if self.speaking and self.player.is_playing():
            QTimer.singleShot(250, self._watch_playback)
        else:
            self._stop_speaking_state()

    def stop_speaking(self) -> None:
        self._speech_token += 1
        if self.speaking:
            self.player.clear()
        self._stop_speaking_state()

    def _stop_speaking_state(self) -> None:
        if self.speaking:
            self.speaking = False
            self.speaking_changed.emit(False)

    # ----- reply mode -----------------------------------------------------------------------------
    def insert(self, text: str) -> str:
        """Paste ``text`` into the window the conversation looked at (after a click); returns
        what happened, for the card. Never sends anything."""
        conversation = self.engine.conversation
        if conversation is None or not conversation.shot.hwnd:
            return "There's no window to insert into."
        return self.paste(conversation.shot.hwnd, text)


class Watcher(QObject):
    """Watch mode: a look every ``watch_interval_s`` while on, stopping by itself."""

    changed = Signal()
    commented = Signal(object)  # WatchResult
    _result = Signal(object)

    def __init__(self, check: WatchCheck, settings, record_skip: Callable[[], None],
                 has_key: Callable[[], bool], wall: Callable[[], float] = time.time) -> None:
        super().__init__()
        self.check = check
        self.settings = settings
        self.record_skip = record_skip
        self.has_key = has_key
        self.wall = wall
        self.running = False
        self.ends_at = 0.0
        self.comments = 0
        self.last_status = ""
        self.error = ""
        self._busy = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._stop_timer = QTimer(self, singleShot=True)
        self._stop_timer.timeout.connect(lambda: self.stop("time"))
        self._result.connect(self._handle)

    def start(self, minutes: int | None = None) -> bool:
        if not self.has_key():
            self.error = "Watch mode needs your Gemini API key (Settings → General)."
            self.changed.emit()
            return False
        assist = self.settings().screen_assist
        minutes = minutes or assist.watch_auto_stop_min
        self.check.reset()
        self.running, self.comments, self.error, self.last_status = True, 0, "", "starting"
        self.ends_at = self.wall() + minutes * 60
        self._timer.start(assist.watch_interval_s * 1000)
        self._stop_timer.start(minutes * 60 * 1000)
        QTimer.singleShot(1500, self._tick)
        log.info("Watch mode on for %d min", minutes)
        self.changed.emit()
        return True

    def stop(self, reason: str = "off") -> None:
        if not self.running:
            return
        self.running = False
        self._timer.stop()
        self._stop_timer.stop()
        self.ends_at = 0.0
        self.last_status = f"stopped ({reason})"
        log.info("Watch mode off (%s); %d looks, %d analysed, %d comments", reason,
                 self.check.checks, self.check.analysed, self.comments)
        self.changed.emit()

    def toggle(self) -> bool:
        if self.running:
            self.stop()
            return False
        return self.start()

    def _tick(self) -> None:
        if not self.running or self._busy:
            return
        self._busy = True

        def work() -> None:
            try:
                self._result.emit(self.check.run())
            except Exception as exc:
                log.exception("Watch mode look failed")
                from wisp.assist.engine import WatchResult

                self._result.emit(WatchResult("error", describe_error(
                    exc, self.check.model.model_name())))

        threading.Thread(target=work, name="watch", daemon=True).start()

    def _handle(self, result) -> None:
        self._busy = False
        if not self.running:
            return
        self.last_status = result.status
        if result.status == "unchanged":
            self.record_skip()
        elif result.status == "comment":
            self.comments += 1
            self.commented.emit(result)
        self.changed.emit()
