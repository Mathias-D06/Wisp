"""Syncing Google Calendar into the offline cache (D-050), following Google's sync guide.

* Full sync: a date window (7 days back, 180 ahead) with singleEvents (recurring events as
  instances); the last page carries nextSyncToken. Repeated weekly, so the window moves on.
* Incremental sync: only syncToken (events.list forbids timeMin/timeMax with it); the pages
  hold every change since, deleted events included ("cancelled").
* 410 GONE: the token is invalid: wipe that calendar and sync it fully again.
* Errors back off 5 → 10 → 20 → 40 → 60 minutes; success returns to every 5 minutes.

``api`` is anything with calendars(), events_page() and insert(): GoogleCalendarApi, or a fake in
tests (Wisp never calls Google in tests or CI).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from wisp.gcal.google import SyncTokenGone
from wisp.gcal.store import CalendarStore

PAST_DAYS = 7
FUTURE_DAYS = 180
FULL_SYNC_EVERY = timedelta(days=7)
INTERVAL_MIN = 5
BACKOFF_MIN = (5, 10, 20, 40, 60)


@dataclass
class SyncResult:
    calendars: int = 0
    changed: int = 0
    removed: int = 0
    full: int = 0  # calendars that needed a full sync


def window(now: datetime) -> tuple[str, str]:
    start = (now - timedelta(days=PAST_DAYS)).astimezone(UTC)
    end = (now + timedelta(days=FUTURE_DAYS)).astimezone(UTC)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


def sync_calendar(api, store: CalendarStore, calendar_id: str, now: datetime,
                  result: SyncResult) -> None:
    token, full_at = store.sync_state(calendar_id)
    if token and full_at and now - full_at > FULL_SYNC_EVERY:
        store.reset_calendar(calendar_id)  # move the window on
        token = None
    if token:
        try:
            _pages(api, store, calendar_id, result, sync_token=token)
            return
        except SyncTokenGone:
            store.reset_calendar(calendar_id)
    else:
        store.reset_calendar(calendar_id)
    result.full += 1
    time_min, time_max = window(now)
    _pages(api, store, calendar_id, result, time_min=time_min, time_max=time_max, full_at=now)


def _pages(api, store: CalendarStore, calendar_id: str, result: SyncResult,
           sync_token: str | None = None, time_min: str | None = None,
           time_max: str | None = None, full_at: datetime | None = None) -> None:
    page = None
    while True:
        response = api.events_page(calendar_id, sync_token=sync_token, page_token=page,
                                   time_min=time_min, time_max=time_max)
        changed, removed = store.apply_events(calendar_id, response.get("items", []))
        result.changed += changed
        result.removed += removed
        page = response.get("nextPageToken")
        if page:
            continue
        store.set_sync_token(calendar_id, response.get("nextSyncToken"), full_at)
        return


def sync_all(api, store: CalendarStore, now: datetime | None = None) -> SyncResult:
    """Refresh the calendar list, then every readable calendar's events."""
    now = now or datetime.now(UTC)
    result = SyncResult()
    store.set_calendars(api.calendars())
    for calendar in store.calendars():
        sync_calendar(api, store, calendar["id"], now, result)
        result.calendars += 1
    store.set_last_synced(now)
    return result


class Backoff:
    """Minutes until the next sync: every 5 minutes, longer after consecutive errors."""

    def __init__(self) -> None:
        self.failures = 0

    def success(self) -> int:
        self.failures = 0
        return INTERVAL_MIN

    def failure(self) -> int:
        self.failures += 1
        return BACKOFF_MIN[min(self.failures, len(BACKOFF_MIN)) - 1]
