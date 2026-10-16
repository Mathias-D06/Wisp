"""Screen Assist without Qt (D-052): capturing safely, the conversation, and Watch mode's check.

Capturer
  The active window by default, or the whole monitor it is on. The blocklist is checked first
  (a blocked active window is never captured); on a whole-screen capture blocked windows are
  painted over. Borders are trimmed and the image downscaled before it is
  encoded. Every capture is written to the Action log (time, window title, mode, size; never
  the image). The image lives in memory for the current exchange only; with Settings → Hotkeys
  and audio → "Save the audio and images sent to Gemini" on, a copy goes to the debug folder.

Conversation
  The turns of one Screen Assist exchange and its follow-ups. A follow-up looks at the window
  again and sends a new screenshot only if the window is a different one or its fingerprint
  (wisp.assist.imaging) moved by more than FOLLOW_UP_CHANGE; otherwise the earlier screenshot
  stands. Only the newest screenshot is sent with the history.

WatchCheck
  One Watch-mode look: skipped when the window hasn't changed meaningfully since the last
  analysed look, otherwise a low-resolution JSON request; comments are throttled.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from PIL import Image

from wisp.assist import imaging, prompts
from wisp.assist.client import AssistModel, Part, Reply, Turn
from wisp.assist.privacy import REFUSAL, Blocklist, mask

log = logging.getLogger(__name__)

CONVERSATION_IDLE_S = 15 * 60  # a question after this long starts a new conversation
MAX_TURNS = 16


class Blocked(Exception):
    """The window is on the blocklist (the message is what Wisp says)."""


class CaptureError(Exception):
    """Nothing to capture (no window, minimised, secure desktop)."""


@dataclass
class Shot:
    jpeg: bytes
    size: tuple[int, int]
    fingerprint: bytes
    hwnd: int
    title: str
    target: str  # "window" | "screen"
    masked: int = 0

    @property
    def what(self) -> str:
        return f"the “{self.title}” window" if self.target == "window" else "the screen"


@dataclass
class WindowSystem:
    """The Windows calls a capture needs (injectable for tests)."""

    foreground: Callable[[], object | None]
    windows: Callable[[], list]
    bounds: Callable[[int], tuple[int, int, int, int] | None]
    monitor_at: Callable[[int, int], tuple[int, int, int, int]]
    grab: Callable[[tuple[int, int, int, int]], Image.Image]
    desktop_available: Callable[[], bool] = lambda: True
    cursor: Callable[[], tuple[int, int]] = lambda: (0, 0)


def real_window_system() -> WindowSystem:
    """The real Windows calls (the app and ``--self-check``)."""
    from wisp.winapi import screen
    from wisp.winapi import windows as win

    return WindowSystem(foreground=win.foreground_window, windows=win.list_windows,
                        bounds=win.frame_bounds, monitor_at=screen.monitor_at, grab=screen.grab,
                        desktop_available=win.input_desktop_available,
                        cursor=screen.cursor_position)


class Capturer:
    def __init__(self, system: WindowSystem, blocklist: Callable[[], Blocklist],
                 log_capture: Callable[[dict], None] = lambda entry: None,
                 save_debug: Callable[[bytes, str], None] = lambda jpeg, label: None,
                 own_pid: int | None = None) -> None:
        self.system = system
        self.blocklist = blocklist
        self.log_capture = log_capture
        self.save_debug = save_debug
        self.own_pid = os.getpid() if own_pid is None else own_pid

    def target_window(self, preferred_hwnd: int | None = None):
        """The window in front, unless it is one of Wisp's own (then ``preferred_hwnd``)."""
        front = self.system.foreground()
        if front is not None and getattr(front, "pid", None) != self.own_pid:
            return front
        if preferred_hwnd:
            for window in self.system.windows():
                if window.hwnd == preferred_hwnd:
                    return window
        return None

    def capture(self, target: str = "window", origin: str = "screen_assist", mode: str = "",
                max_edge: int = imaging.MAX_EDGE, preferred_hwnd: int | None = None) -> Shot:
        """Raises Blocked or CaptureError; anything unexpected (a Windows call, the image
        steps) is logged with its traceback and becomes a CaptureError with its message."""
        try:
            return self._capture(target, origin, mode, max_edge, preferred_hwnd)
        except (Blocked, CaptureError):
            raise
        except Exception as exc:
            log.exception("Screen capture failed")
            raise CaptureError(f"Wisp couldn't take the screenshot ({type(exc).__name__}: "
                               f"{exc}).") from exc

    def _capture(self, target: str, origin: str, mode: str, max_edge: int,
                 preferred_hwnd: int | None) -> Shot:
        if not self.system.desktop_available():
            raise CaptureError("Windows is showing a secure screen (sign-in or a permission "
                               "prompt), which apps can't see.")
        window = self.target_window(preferred_hwnd)
        rules = self.blocklist()
        if window is None and target == "window":
            raise CaptureError("There's no window to look at.")
        if window is not None:
            reason = rules.reason(window.process, window.title)
            if reason:
                self.log_capture({"origin": origin, "target": target, "mode": mode,
                                  "window": window.title, "blocked": reason})
                raise Blocked(REFUSAL)
        bounds = self.system.bounds(window.hwnd) if window is not None else None
        if target == "window" and (bounds is None or getattr(window, "minimized", False)):
            raise CaptureError("That window is minimised or off-screen.")
        masked = 0
        if target == "screen":
            x, y = (((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2) if bounds
                    else self.system.cursor())
            region = self.system.monitor_at(x, y)
            image = self.system.grab(region)
            hidden = [rect for other in self.system.windows()
                      if not getattr(other, "minimized", False) and rules.blocks(other)
                      and (rect := self.system.bounds(other.hwnd))]
            image, masked = mask(image, region, hidden)
        else:
            image = self.system.grab(bounds)
        small = imaging.downscale(imaging.trim(image), max_edge)
        data = imaging.jpeg(small)
        title = window.title if window is not None else ""
        shot = Shot(data, small.size, imaging.fingerprint(small),
                    window.hwnd if window is not None else 0, title, target, masked)
        self.log_capture({"origin": origin, "target": target, "mode": mode, "window": title,
                          "pixels": f"{small.size[0]}x{small.size[1]}", "masked": masked})
        self.save_debug(data, origin)
        return shot


@dataclass
class Exchange:
    question: str
    answer: str
    shot: Shot
    mode: str = ""
    recaptured: bool = False  # a follow-up that needed a new screenshot
    follow_up: bool = False
    reply: Reply | None = None


@dataclass
class Conversation:
    shot: Shot
    turns: list[Turn] = field(default_factory=list)
    last_used: float = 0.0
    target: str = "window"

    def request_turns(self) -> list[Turn]:
        """The history to send: the last MAX_TURNS turns, only the newest screenshot."""
        turns = self.turns[-MAX_TURNS:]
        newest = max((i for i, t in enumerate(turns) if any(p.jpeg for p in t.parts)),
                     default=-1)
        trimmed = []
        for index, turn in enumerate(turns):
            parts = [part if (not part.jpeg or index == newest)
                     else Part(text="[an earlier screenshot, no longer shown]")
                     for part in turn.parts]
            trimmed.append(Turn(turn.role, parts))
        return trimmed


class AssistEngine:
    def __init__(self, model: AssistModel, capturer: Capturer, language: Callable[[], str],
                 on_usage: Callable[[str, Reply], None] = lambda feature, reply: None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.model = model
        self.capturer = capturer
        self.language = language
        self.on_usage = on_usage
        self.clock = clock
        self.conversation: Conversation | None = None

    def reset(self) -> None:
        self.conversation = None

    def active(self) -> bool:
        conversation = self.conversation
        return (conversation is not None
                and self.clock() - conversation.last_used < CONVERSATION_IDLE_S)

    def ask(self, question: str | None = None, mode: str | None = None,
            target: str | None = None, audio_wav: bytes = b"", new: bool = False,
            detailed: bool = False, origin: str = "screen_assist",
            shot: Shot | None = None) -> Exchange:
        """Answer about the screen. A new conversation captures; a follow-up re-captures only
        if the window changed. ``shot``: a capture already taken (the hotkey takes it the
        moment it's pressed). Raises Blocked, CaptureError or the model's errors."""
        follow_up = not new and self.active() and (target is None
                                                   or target == self.conversation.target)
        target = target or (self.conversation.target if follow_up else "window")
        if audio_wav and not (question or "").strip():
            text = " ".join(filter(None, (prompts.MODES.get(mode, ("", ""))[1],
                                          prompts.AUDIO_QUESTION)))
        else:
            text = prompts.question_text(question, mode)
        recaptured = False
        if follow_up:
            conversation = self.conversation
            shot = shot or self.capturer.capture(target, origin, mode or "follow-up",
                                                 preferred_hwnd=conversation.shot.hwnd)
            changed = (shot.hwnd != conversation.shot.hwnd
                       or imaging.changed(conversation.shot.fingerprint, shot.fingerprint,
                                          imaging.FOLLOW_UP_CHANGE))
            parts = [Part(text=text)]
            if changed:
                parts.append(Part(text=prompts.CHANGED_INTRO.format(what=shot.what),
                                  jpeg=shot.jpeg))
                conversation.shot = shot
                recaptured = True
        else:
            shot = shot or self.capturer.capture(target, origin, mode or "explain")
            conversation = Conversation(shot, target=target)
            self.conversation = conversation
            parts = [Part(text=text),
                     Part(text=prompts.SCREEN_INTRO.format(what=shot.what), jpeg=shot.jpeg)]
        if audio_wav:
            parts.append(Part(wav=audio_wav))
        conversation.turns.append(Turn("user", parts))
        conversation.last_used = self.clock()
        try:
            reply = self.model.answer(conversation.request_turns(),
                                      prompts.system_instruction(self.language(), detailed))
        except Exception:
            conversation.turns.pop()  # the question can be asked again
            raise
        conversation.turns.append(Turn("model", [Part(text=reply.text)]))
        self.on_usage("screen_assist", reply)
        return Exchange(question or (prompts.MODES[mode][0] if mode in prompts.MODES else ""),
                        reply.text.strip(), conversation.shot, mode or "", recaptured,
                        follow_up, reply)

    def more(self) -> Exchange:
        return self.ask(prompts.MORE, detailed=True)


@dataclass
class WatchResult:
    status: str  # unchanged | blocked | nothing | silent | throttled | comment | error
    text: str = ""
    shot: Shot | None = None


class WatchCheck:
    """One Watch-mode look at the active window."""

    def __init__(self, model: AssistModel, capturer: Capturer,
                 comment_gap_s: Callable[[], float],
                 on_usage: Callable[[str, Reply], None] = lambda feature, reply: None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.model = model
        self.capturer = capturer
        self.comment_gap_s = comment_gap_s
        self.on_usage = on_usage
        self.clock = clock
        self.last_fingerprint: bytes | None = None
        self.last_hwnd = 0
        self.last_comment_at = -1e9
        self.last_comment = ""
        self.checks = self.analysed = 0

    def reset(self) -> None:
        self.last_fingerprint, self.last_hwnd = None, 0
        self.last_comment_at, self.last_comment = -1e9, ""
        self.checks = self.analysed = 0

    def run(self) -> WatchResult:
        self.checks += 1
        try:
            shot = self.capturer.capture("window", "watch", "watch",
                                         max_edge=imaging.WATCH_MAX_EDGE)
        except Blocked:
            return WatchResult("blocked")
        except CaptureError:
            return WatchResult("nothing")
        if shot.hwnd == self.last_hwnd and not imaging.changed(
                self.last_fingerprint, shot.fingerprint, imaging.WATCH_CHANGE):
            return WatchResult("unchanged", shot=shot)
        self.last_fingerprint, self.last_hwnd = shot.fingerprint, shot.hwnd
        self.analysed += 1
        turn = Turn("user", [Part(text=prompts.SCREEN_INTRO.format(what=shot.what),
                                  jpeg=shot.jpeg)])
        reply = self.model.answer([turn], prompts.WATCH, json_schema=prompts.WATCH_SCHEMA,
                                  low_resolution=True)
        self.on_usage("watch", reply)
        verdict = parse_verdict(reply.text)
        if verdict is None:
            return WatchResult("silent", shot=shot)
        if verdict == self.last_comment:
            return WatchResult("silent", shot=shot)
        now = self.clock()
        if now - self.last_comment_at < self.comment_gap_s():
            return WatchResult("throttled", verdict, shot)
        self.last_comment_at, self.last_comment = now, verdict
        return WatchResult("comment", verdict, shot)


def parse_verdict(text: str) -> str | None:
    """The comment from Watch mode's JSON, or None when there's nothing to say."""
    try:
        data = json.loads(text or "{}")
    except ValueError:
        log.info("Watch mode: reply wasn't JSON")
        return None
    if not isinstance(data, dict) or data.get("comment") is not True:
        return None
    comment = str(data.get("text") or "").strip()
    return comment[:400] or None
