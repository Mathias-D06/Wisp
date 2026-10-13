"""The island's state machine (D-045): what the island shows, decided in one place.

Services report what they are doing (voice, dictation, media, reminders, notifications) and the
user's hover/expand actions; the machine turns that into a ``Presentation``: one of the shapes
idle, activity (with an optional split-off second activity), banner, expanded, away (auto-hidden
after a quiet spell, D-049) or hidden (a full-screen app is in front).

Priority, highest first (TIERS): active voice > banner > timer > music > idle. Banners wait in
a short queue while voice is active and show one at a time. The user's own actions win over all
of it: an expanded island stays expanded, and a full-screen app hides the island.

Pure Python with an injectable clock, so tests can drive time directly.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from wisp.ui.theme import ISLAND, IslandTokens

TIERS = ("voice", "banner", "timer", "music", "idle")  # priority, highest first
VOICE_KINDS = ("listening", "thinking", "speaking")
METERS = {"listening": "mic", "speaking": "output"}


@dataclass(frozen=True)
class Activity:
    """Something live, shown at a glance: kind decides the content, tier the priority."""

    kind: str  # listening | thinking | speaking | dictation | status | music | countdown
    tier: str  # voice | timer | music
    text: str = ""
    tone: str = "accent"  # theme tone for the icon/orb: accent, success, warning, danger, muted
    meter: str | None = None  # which level the view draws: mic | output | dictation | media
    data: object = None  # MediaState for music, due time (epoch seconds) for countdown


@dataclass(frozen=True)
class Banner:
    id: int
    title: str
    line: str = ""
    icon: str = "info"
    tone: str = "accent"
    created: float = 0.0
    action: Callable[[], None] | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Presentation:
    mode: str  # hidden | away | idle | activity | banner | expanded
    main: Activity | None = None
    secondary: Activity | None = None  # split: shown as the detached circle
    banner: Banner | None = None

    @property
    def content_key(self) -> tuple:
        """Changes when the content (not just its text or level) changes."""
        return (self.mode, self.main.kind if self.main else None,
                self.secondary.kind if self.secondary else None,
                self.banner.id if self.banner else None)


def tier_rank(tier: str) -> int:
    return TIERS.index(tier)


class IslandStateMachine:
    def __init__(self, tokens: IslandTokens = ISLAND, clock: Callable[[], float] = time.monotonic):
        self.tokens = tokens
        self.clock = clock
        self._voice: Activity | None = None
        self._override: Activity | None = None  # dictation, Circle to Ask, short status
        self._override_until: float | None = None
        self._music: Activity | None = None
        self._timer: Activity | None = None
        self._queue: list[Banner] = []
        self._showing: Banner | None = None
        self._banner_until = 0.0
        self._ids = itertools.count(1)
        self.expanded = False
        self.hidden = False
        self.hovered = False
        self.confirming = False  # a confirmation card is waiting
        self.autohide = False
        self.autohide_ms = tokens.autohide_ms
        self.keep_for_music = True
        self._idle_since = clock()
        self._was_hideable = False
        self._resume_away = False
        self._listeners: list[Callable[[Presentation], None]] = []
        self._deadline_listeners: list[Callable[[], None]] = []
        self.presentation = Presentation("idle")

    # ----- listeners ---------------------------------------------------------------------------
    def subscribe(self, listener: Callable[[Presentation], None]) -> None:
        self._listeners.append(listener)

    def subscribe_deadline(self, listener: Callable[[], None]) -> None:
        """Called after every change: the next deadline may have moved even when the
        presentation didn't (a banner's hold extended on hover, the quiet spell restarted)."""
        self._deadline_listeners.append(listener)

    def _changed(self) -> None:
        now = self.clock()
        self._advance(now)
        hideable = self.hideable()
        if hideable and not self._was_hideable:
            self._idle_since = now  # the quiet spell starts now
        self._was_hideable = hideable
        new = self._compute(now)
        old = self.presentation
        if new != old:
            self.presentation = new
            for listener in list(self._listeners):
                listener(new)
        for listener in list(self._deadline_listeners):
            listener()

    def update(self) -> None:
        """Process timeouts (banner hold, short statuses, auto-hide); call when a deadline
        from ``next_deadline`` passes."""
        self._changed()

    def next_deadline(self) -> float | None:
        """When the presentation may change without a new event (clock seconds), or None."""
        now = self.clock()
        times = []
        if self._override_until is not None:
            times.append(self._override_until)
        if self._showing is not None and not self.hovered and self._voice_activity() is None:
            times.append(self._banner_until)
        if self.hideable() and self.presentation.mode != "away":
            times.append(self._idle_since + self.autohide_ms / 1000)
        future = [t for t in times if t > now]
        return min(future) if future else (now if times else None)

    # ----- reports from services ---------------------------------------------------------------
    def set_voice(self, state: str, text: str = "") -> None:
        """The voice controller's orb state: listening, thinking or speaking are active voice;
        idle, offline and error are not (errors arrive as banners)."""
        if state in VOICE_KINDS:
            self._voice = Activity(state, "voice", text, meter=METERS.get(state))
        else:
            self._voice = None
        self._changed()

    def show_status(self, kind: str, text: str, tone: str = "accent", meter: str | None = None,
                    ms: int | None = None) -> None:
        """A voice-tier activity owned by dictation or Circle to Ask (``ms``: clears itself)."""
        self._override = Activity(kind, "voice", text, tone, meter)
        self._override_until = None if ms is None else self.clock() + ms / 1000
        self._changed()

    def clear_status(self) -> None:
        self._override, self._override_until = None, None
        self._changed()

    def set_music(self, state) -> None:
        """A MediaState; only playing media is a live activity."""
        playing = state is not None and state.active and state.playing
        if playing:
            label = state.title + (f" — {state.artist}" if state.artist else "")
            self._music = Activity("music", "music", label, meter="media", data=state)
        else:
            self._music = None
        self._changed()

    def set_countdown(self, title: str | None, due: float | None = None) -> None:
        """A reminder or routine due soon (``due``: epoch seconds), or None."""
        self._timer = (Activity("countdown", "timer", title, data=due)
                       if title and due is not None else None)
        self._changed()

    def post(self, title: str, line: str = "", icon: str = "info", tone: str = "accent",
             action: Callable[[], None] | None = None) -> Banner:
        """Queue a banner. The same title and line already waiting (or showing) is refreshed
        instead of repeated; the queue keeps the newest ``banner_queue`` banners."""
        now = self.clock()
        for index, waiting in enumerate(self._queue):
            if (waiting.title, waiting.line) == (title, line):
                self._queue[index] = replace(waiting, created=now, action=action)
                self._changed()
                return self._queue[index]
        if self._showing is not None and (self._showing.title, self._showing.line) == (title, line):
            self._banner_until = now + self.tokens.banner_hold_ms / 1000
            self._changed()
            return self._showing
        banner = Banner(next(self._ids), title, line, icon, tone, now, action)
        self._queue.append(banner)
        del self._queue[:-self.tokens.banner_queue]
        self._changed()
        return banner

    def dismiss(self) -> None:
        """Drop the banner on screen (click, swipe up); the next one may follow."""
        self._showing = None
        self._changed()

    # ----- the user ----------------------------------------------------------------------------
    def set_hover(self, hovered: bool) -> None:
        if hovered == self.hovered:
            return
        self.hovered = hovered
        now = self.clock()
        self._idle_since = now
        if not hovered and self._showing is not None:
            extra = self.tokens.banner_hover_extra_ms / 1000
            self._banner_until = max(self._banner_until, now + extra)
        self._changed()

    def expand(self) -> None:
        self.expanded = True
        self._changed()

    def collapse(self) -> None:
        self.expanded = False
        self._changed()

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self._changed()

    def set_hidden(self, hidden: bool) -> None:
        """A full-screen app is in front (or no longer). If the island had slid away, it
        goes straight back to away afterwards instead of reappearing for a while."""
        if hidden and self.presentation.mode == "away":
            self._resume_away = True
        self.hidden = hidden
        if hidden:
            self.expanded = False
        elif self._resume_away:
            self._resume_away = False
            self._was_hideable = True  # keep the old quiet spell
        self._changed()

    def set_autohide(self, enabled: bool, after_ms: int | None = None,
                     keep_for_music: bool | None = None) -> None:
        """Hide the idle island after ``after_ms`` (Settings → General)."""
        self.autohide = enabled
        if after_ms is not None:
            self.autohide_ms = after_ms
        if keep_for_music is not None:
            self.keep_for_music = keep_for_music
        self._idle_since = self.clock()
        self._changed()

    def set_confirming(self, confirming: bool) -> None:
        """A confirmation card is waiting: never hide meanwhile."""
        self.confirming = confirming
        self._changed()

    def reveal(self) -> None:
        """The pointer rested in the reveal zone: show the island and start the quiet spell
        over (it hides again after the delay, once the pointer isn't on it)."""
        self._idle_since = self.clock()
        self._changed()

    def hideable(self) -> bool:
        """May the island hide now? Only when auto-hide is on and nothing is going on: no voice,
        dictation or status, no banner (showing or queued), no countdown, no confirmation, not
        expanded or under the pointer, and no music unless keep_for_music is off."""
        if not self.autohide or self.hidden or self.expanded or self.hovered or self.confirming:
            return False
        if self._voice_activity() is not None or self._timer is not None:
            return False
        if self._showing is not None or self._queue:
            return False
        return self._music is None or not self.keep_for_music

    # ----- internals ---------------------------------------------------------------------------
    def _voice_activity(self) -> Activity | None:
        return self._override or self._voice

    def _advance(self, now: float) -> None:
        if self._override_until is not None and now >= self._override_until:
            self._override, self._override_until = None, None
        voice = self._voice_activity()
        if self._showing is not None:
            if voice is not None:
                # Active voice outranks banners: put it back at the front; it starts over later.
                self._queue.insert(0, self._showing)
                self._showing = None
            elif self.hovered:
                extra = self.tokens.banner_hover_extra_ms / 1000
                self._banner_until = max(self._banner_until, now + extra)
            elif now >= self._banner_until:
                self._showing = None
        if self._showing is None and voice is None and not self.expanded:
            max_age = self.tokens.banner_max_age_ms / 1000
            while self._queue:
                banner = self._queue.pop(0)
                if now - banner.created <= max_age:
                    self._showing = banner
                    self._banner_until = now + self.tokens.banner_hold_ms / 1000
                    break

    def _compute(self, now: float) -> Presentation:
        if self.hidden:
            return Presentation("hidden")
        live = [a for a in (self._voice_activity(), self._timer, self._music) if a is not None]
        live.sort(key=lambda activity: tier_rank(activity.tier))
        if self.expanded:
            return Presentation("expanded", main=live[0] if live else None)
        if self._showing is not None:
            return Presentation("banner", banner=self._showing)
        if self.hideable() and now - self._idle_since >= self.autohide_ms / 1000:
            return Presentation("away")
        if live:
            return Presentation("activity", main=live[0],
                                secondary=live[1] if len(live) > 1 else None)
        return Presentation("idle")


def pick_countdown(items, now, window_s: int = ISLAND.countdown_window_s):
    """The soonest (title, due) among ``items`` that falls within ``window_s`` seconds of
    ``now`` (datetimes; naive ones are local time), as (title, epoch seconds), or None."""
    soon = []
    for title, due in items:
        if due is None:
            continue
        seconds = due.timestamp() - now.timestamp()
        if 0 < seconds <= window_s:
            soon.append((due.timestamp(), title))
    if not soon:
        return None
    due, title = min(soon)
    return title, due
