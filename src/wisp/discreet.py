"""Discreet mode (D-053): Wisp stays fully usable but much less noticeable, for lectures,
libraries and meetings.

This module decides whether Discreet mode is on; the app applies what it means (the island's
line or dot, text-only answers on a quiet card, banners as a pulse, no Windows notifications,
push-to-talk only). It's on when the person turned it on (Settings, the island's menu, the tray,
voice "go discreet", Ctrl+Alt+D; remembered across restarts), or, with "During calendar
events" on, while a timed Google Calendar event is under way. Turning it off during an event
keeps it off until that event ends.

It is a visual and sound setting only. Wisp's windows stay ordinary windows: nothing is hidden
from screen capture or screen sharing, and nothing interferes with other software.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)

SCHEDULE_CHECK_MS = 60_000


@dataclass(frozen=True)
class DiscreetLook:
    """What the island needs to know."""

    style: str = "line"  # "line" | "dot"
    opacity: float = 0.5
    position: str = "top-centre"


class DiscreetMode(QObject):
    changed = Signal(bool)

    def __init__(self, settings_store, calendar=None,
                 now: Callable[[], datetime] = lambda: datetime.now().astimezone()) -> None:
        super().__init__()
        self.settings_store = settings_store
        self.calendar = calendar
        self.now = now
        self.manual = bool(settings_store.peek().discreet.enabled)
        self.auto = False
        self._declined_event = ""  # turned off during this event: stay off until it ends
        self._timer = QTimer(self, interval=SCHEDULE_CHECK_MS)
        self._timer.timeout.connect(self.check_schedule)
        self._timer.start()

    @property
    def active(self) -> bool:
        return self.manual or self.auto

    def profile(self):
        return self.settings_store.peek().discreet

    def look(self) -> DiscreetLook | None:
        if not self.active:
            return None
        profile = self.profile()
        return DiscreetLook(profile.style, profile.opacity / 100, profile.position)

    def set_enabled(self, on: bool, source: str = "ui") -> None:
        before = self.active
        if not on and self.auto:
            current = self._current_event()
            self._declined_event = current.id if current is not None else ""
            self.auto = False
        self.manual = on
        if self.profile().enabled != on:
            self.settings_store.update(lambda s: setattr(s.discreet, "enabled", on))
        log.info("Discreet mode %s (%s)", "on" if on else "off", source)
        if self.active != before:
            self.changed.emit(self.active)

    def toggle(self, source: str = "ui") -> bool:
        self.set_enabled(not self.active, source)
        return self.active

    def _current_event(self):
        calendar = self.calendar
        if calendar is None or not calendar.connected:
            return None
        now = self.now()
        running = [event for event in calendar.events(now, now + timedelta(seconds=1))
                   if not event.all_day and event.start <= now < event.end]
        return min(running, key=lambda event: event.end) if running else None

    def check_schedule(self) -> None:
        """Every minute: on during a timed calendar event (if that setting is on)."""
        before = self.active
        event = self._current_event() if self.profile().during_events else None
        if event is None:
            self.auto, self._declined_event = False, ""
        elif event.id != self._declined_event:
            if not self.auto:
                log.info("Discreet mode on during a calendar event")
            self.auto = True
        if self.active != before:
            self.changed.emit(self.active)
