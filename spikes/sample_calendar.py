"""Dev helper: fill a CalendarService with a made-up calendar for screenshots and recordings.

The service gets an in-memory "token" (so it counts as connected) and an API factory that refuses
to run, so nothing here can reach Google or write to the data folder's token file. Events are
placed relative to today, in Europe/London.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from wisp.gcal.google import SCOPES_READ
from wisp.gcal.times import localize, zone

LONDON = zone("Europe/London")
CALENDARS = [
    {"id": "me", "summary": "Sam", "backgroundColor": "#4285f4", "primary": True,
     "selected": True, "accessRole": "owner", "timeZone": "Europe/London"},
    {"id": "work", "summary": "Work", "backgroundColor": "#e67c73", "selected": True,
     "accessRole": "writer", "timeZone": "Europe/London"},
    {"id": "family", "summary": "Family", "backgroundColor": "#33b679", "selected": True,
     "accessRole": "writer", "timeZone": "Europe/London"},
]
# (calendar, day offset, "HH:MM" start or None for all-day, minutes or days, title)
EVENTS = [
    ("work", 0, "09:30", 15, "Standup"),
    ("me", 0, "15:00", 45, "Dentist"),
    ("work", 0, "16:00", 30, "Call with Ana"),
    ("family", 1, None, 1, "Bin day"),
    ("work", 1, "11:00", 60, "Design review"),
    ("me", 2, "18:30", 90, "Climbing"),
    ("family", 3, None, 3, "Half-term"),
    ("me", 4, "19:00", 120, "Dinner at Rosa's"),
    ("work", 6, "10:00", 60, "Sprint planning"),
    ("me", 9, "08:00", 30, "Car MOT"),
    ("family", 12, "13:00", 180, "Grandma's birthday lunch"),
    ("work", 15, "14:00", 60, "Quarterly review"),
]


class _Secret:
    def __init__(self, value: dict) -> None:
        self.value = value

    def load(self) -> dict:
        return self.value

    def exists(self) -> bool:
        return True

    def save(self, value: dict) -> None:
        self.value = value

    def clear(self) -> None:
        pass


def _offline(_info):
    raise RuntimeError("sample calendar: no network")


def fill(service, now: datetime | None = None) -> None:
    now = (now or datetime.now(LONDON)).astimezone(LONDON)
    service._token_file = _Secret({"token": "sample", "scopes": list(SCOPES_READ)})
    service._client_file = _Secret({"installed": {"client_id": "sample.apps.googleusercontent"
                                                                ".com"}})
    service._api_factory = _offline
    service.tab_opened = lambda: None  # no sync attempts: the sample stays "synced 2 min ago"
    service.sync_now = lambda: False
    store = service.store
    store.set_calendars(CALENDARS)
    today = now.date()
    for index, (calendar, offset, start, length, title) in enumerate(EVENTS):
        day = today + timedelta(days=offset)
        if start is None:
            when = {"start": {"date": day.isoformat()},
                    "end": {"date": (day + timedelta(days=length)).isoformat()}}
        else:
            hour, minute = map(int, start.split(":"))
            begin = localize(datetime(day.year, day.month, day.day, hour, minute), LONDON)
            when = {"start": {"dateTime": begin.isoformat()},
                    "end": {"dateTime": (begin + timedelta(minutes=length)).isoformat()}}
        store.apply_events(calendar, [{"id": f"sample{index}", "status": "confirmed",
                                       "summary": title, **when,
                                       "htmlLink": "https://calendar.google.com/"}])
    store.set_last_synced(now - timedelta(minutes=2))
    service.changed.emit()
