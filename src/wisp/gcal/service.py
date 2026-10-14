"""Google Calendar for Wisp (D-050): connection state, background sync, and what the Calendar
tab, the voice tools and the island ask of it.

Network work (sign-in, sync, revoke, adding an event) runs on threads; results come back to the
Qt thread through signals. The OAuth client and the tokens live in DPAPI-encrypted files and
are never logged. Credentials refreshed by google-auth during a sync are saved back.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from wisp.gcal import google
from wisp.gcal.store import OWNED, CalendarStore
from wisp.gcal.sync import Backoff, sync_all
from wisp.gcal.times import Event, event_from_item, zone

log = logging.getLogger(__name__)

STALE_S = 60  # opening the tab syncs when the last sync is older than this


class CalendarService(QObject):
    changed = Signal()  # events or connection state changed: refresh views
    _done = Signal(str, object, object)  # job, result, error (from worker threads)

    def __init__(self, store: CalendarStore, client_file, token_file,
                 api_factory=google.GoogleCalendarApi, authorize=google.authorize,
                 revoke=google.revoke, now=lambda: datetime.now(UTC)):
        super().__init__()
        self.store = store
        self._client_file = client_file
        self._token_file = token_file
        self._api_factory = api_factory
        self._authorize = authorize
        self._revoke = revoke
        self._now = now
        self._busy: str | None = None  # "connect" | "sync" | "disconnect"
        self.error = ""
        self.needs_reconnect = False
        self._backoff = Backoff()
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.sync_now)
        self._done.connect(self._finished)

    # ----- state -------------------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._token_file.exists()

    @property
    def busy(self) -> str | None:
        return self._busy

    def state(self) -> str:
        """disconnected | connecting | reconnect | error | syncing | connected"""
        if self._busy == "connect":
            return "connecting"
        if not self.connected:
            return "disconnected"
        if self.needs_reconnect:
            return "reconnect"
        if self._busy == "sync":
            return "syncing"
        return "error" if self.error else "connected"

    def has_client(self) -> bool:
        return self._client_file.exists()

    def client_label(self) -> str:
        config = self._client_file.load()
        return google.client_label(config) if config else ""

    def can_create(self) -> bool:
        return google.SCOPE_CREATE in google.granted(self._token_file.load())

    def time_zone(self) -> str | None:
        return self.store.time_zone()

    def tz(self):
        return zone(self.time_zone())

    # ----- the OAuth client ---------------------------------------------------------------------
    def import_client(self, text: str) -> str:
        """Save a Desktop app client JSON; returns its label. Raises CalendarError."""
        config = google.parse_client(text)
        self._client_file.save(config)
        self.changed.emit()
        return google.client_label(config)

    def remove_client(self) -> None:
        self._client_file.clear()
        self.changed.emit()

    # ----- connect / disconnect ------------------------------------------------------------------
    def connect_account(self, allow_create: bool) -> bool:
        """Open the browser sign-in (on a thread). False if no client is set or busy."""
        config = self._client_file.load()
        if config is None or self._busy:
            return False
        scopes = google.scopes_for(allow_create)
        self._start("connect", lambda: self._authorize(config, scopes))
        return True

    def disconnect(self) -> None:
        """Revoke the token at Google, then forget it and the cached calendar."""
        info = self._token_file.load()
        self._token_file.clear()
        self.store.clear()
        self.needs_reconnect = False
        self.error = ""
        self._timer.stop()
        self.changed.emit()
        if info:
            self._start("disconnect", lambda: self._revoke(info))

    # ----- sync ----------------------------------------------------------------------------------
    def sync_now(self) -> bool:
        info = self._token_file.load()
        if info is None or self._busy or self.needs_reconnect:
            return False

        def work():
            api = self._api_factory(info)
            result = sync_all(api, self.store, self._now())
            return result, api.info()

        self._start("sync", work)
        return True

    def tab_opened(self) -> None:
        """The Calendar tab came into view: sync if the cache is more than a minute old."""
        last = self.store.last_synced()
        if last is None or (self._now() - last).total_seconds() > STALE_S:
            self.sync_now()

    def start(self) -> None:
        """At start-up: sync soon if connected."""
        if self.connected:
            self._timer.start(3000)

    def _schedule(self, minutes: int) -> None:
        self._timer.start(minutes * 60_000)

    # ----- threads -------------------------------------------------------------------------------
    def _start(self, job: str, work) -> None:
        self._busy = job
        self.changed.emit()

        def run():
            try:
                self._done.emit(job, work(), None)
            except Exception as exc:  # reported on the Qt thread
                self._done.emit(job, None, exc)

        threading.Thread(target=run, name=f"gcal-{job}", daemon=True).start()

    def _finished(self, job: str, result, error) -> None:
        self._busy = None
        if job == "connect":
            if error is None:
                self._token_file.save(result)
                self.needs_reconnect = False
                self.error = ""
                log.info("Google Calendar connected")
                self.sync_now()
            else:
                self.error = str(error) if isinstance(error, google.CalendarError) else \
                    f"Google sign-in failed ({type(error).__name__})."
                log.warning("Google Calendar connect failed: %s", type(error).__name__)
        elif job == "sync":
            if error is None:
                summary, info = result
                if info and info != self._token_file.load():
                    self._token_file.save(info)  # refreshed access token
                self.error = ""
                log.info("Calendar synced: %d calendars, %d changed, %d removed",
                         summary.calendars, summary.changed, summary.removed)
                self._schedule(self._backoff.success())
            elif isinstance(error, google.AuthExpired):
                self.needs_reconnect = True
                self.error = str(error)
                log.warning("Google Calendar sign-in expired")
            else:
                self.error = str(error) if isinstance(error, google.CalendarError) else \
                    f"Calendar sync failed ({type(error).__name__})."
                log.warning("Calendar sync failed: %s", type(error).__name__)
                self._schedule(self._backoff.failure())
        elif job == "disconnect":
            log.info("Google Calendar disconnected (revoked=%s)", bool(result))
        self.changed.emit()

    # ----- reading -------------------------------------------------------------------------------
    def events(self, start: datetime, end: datetime) -> list[Event]:
        return self.store.events_between(start, end)

    def next_event(self, now: datetime, within_min: int) -> Event | None:
        """The next timed event starting within ``within_min`` minutes (for the island)."""
        if within_min <= 0:
            return None
        upcoming = [e for e in self.events(now, now + timedelta(minutes=within_min))
                    if not e.all_day and e.start > now]
        return min(upcoming, key=lambda e: e.start) if upcoming else None

    # ----- adding an event (the calendar_create tool; runs on a worker thread) -----------------
    def writable_calendar(self, name: str | None) -> dict:
        calendar = self.store.find_calendar(name)
        if calendar is None:
            raise google.CalendarError(f"There's no calendar called “{name}”.")
        if calendar["access_role"] not in OWNED:
            raise google.CalendarError(f"Wisp can't add events to “{calendar['title']}” "
                                       "(you don't own it).")
        return calendar

    def create(self, calendar_id: str, body: dict) -> Event:
        info = self._token_file.load()
        if info is None:
            raise google.CalendarError("Connect Google Calendar in Settings → Accounts first.")
        if google.SCOPE_CREATE not in google.granted(info):
            raise google.MissingPermission("Wisp isn't allowed to add events. Tick “Let Wisp "
                                           "add events” in Settings → Accounts and connect "
                                           "again.")
        api = self._api_factory(info)
        item = api.insert(calendar_id, body)
        self.store.apply_events(calendar_id, [item])
        refreshed = api.info()
        if refreshed != info:
            self._token_file.save(refreshed)
        self.changed.emit()
        return event_from_item(calendar_id, item)
