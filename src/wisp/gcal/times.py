"""Event times for the Calendar tab and tools (D-050).

Google gives timed events as RFC3339 date-times with an offset (``start.dateTime``) and all-day
events as dates (``start.date``, the end date exclusive). Timed events are stored in UTC and
shown in the user's zone: the primary calendar's IANA zone (for example Europe/London), or the
system's local zone. zoneinfo does the daylight-saving arithmetic, so an event in the hour that
repeats when the clocks go back keeps its real order and shows the right wall time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone(name: str | None) -> tzinfo:
    """The IANA zone ``name``, or the system's local zone."""
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return datetime.now().astimezone().tzinfo


def parse_point(value: dict, default_zone: tzinfo | None = None) -> tuple[datetime | None,
                                                                          date | None]:
    """A Google start/end object → (UTC datetime, None) for timed, (None, date) for all-day."""
    if value.get("dateTime"):
        moment = datetime.fromisoformat(value["dateTime"])
        if moment.tzinfo is None:  # only allowed together with timeZone
            moment = moment.replace(tzinfo=zone(value.get("timeZone")) if value.get("timeZone")
                                    else default_zone or UTC)
        return moment.astimezone(UTC), None
    if value.get("date"):
        return None, date.fromisoformat(value["date"])
    raise ValueError("event time has neither dateTime nor date")


@dataclass(frozen=True)
class Event:
    calendar_id: str
    id: str
    title: str
    all_day: bool
    start: datetime | None  # UTC, timed events
    end: datetime | None
    start_date: date | None  # all-day events; end_date is exclusive
    end_date: date | None
    link: str = ""
    location: str = ""
    color: str = ""  # the calendar's colour from Google ("" → the accent)

    def local_start(self, tz: tzinfo) -> datetime:
        if self.all_day:
            return datetime.combine(self.start_date, datetime.min.time(), tz)
        return self.start.astimezone(tz)

    def days(self, tz: tzinfo) -> list[date]:
        """The local dates this event touches."""
        if self.all_day:
            last = self.end_date - timedelta(days=1)
            first = self.start_date
        else:
            first = self.start.astimezone(tz).date()
            end = self.end.astimezone(tz)
            last = (end - timedelta(microseconds=1)).date() if end > self.start else first
        if last < first:
            last = first
        return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def event_from_item(calendar_id: str, item: dict, default_zone: tzinfo | None = None) -> Event:
    start, start_date = parse_point(item.get("start", {}), default_zone)
    end, end_date = parse_point(item.get("end", {}), default_zone)
    all_day = start_date is not None
    if all_day and end_date is None:
        end_date = start_date + timedelta(days=1)
    if not all_day and end is None:
        end = start
    return Event(calendar_id, item["id"], item.get("summary") or "(No title)", all_day, start,
                 end, start_date, end_date, item.get("htmlLink", ""), item.get("location", ""))


def sort_key(event: Event, tz: tzinfo) -> tuple:
    """All-day events first, then by start time, then by title."""
    return (0 if event.all_day else 1, event.local_start(tz), event.title.lower())


def agenda(events: list[Event], first_day: date, days: int, tz: tzinfo,
           ) -> list[tuple[date, list[Event]]]:
    """Events grouped by local day for ``days`` days from ``first_day`` (empty days left out)."""
    last_day = first_day + timedelta(days=days - 1)
    by_day: dict[date, list[Event]] = {}
    for event in events:
        for day in event.days(tz):
            if first_day <= day <= last_day:
                by_day.setdefault(day, []).append(event)
    return [(day, sorted(by_day[day], key=lambda e: sort_key(e, tz))) for day in sorted(by_day)]


def span_text(event: Event, day: date, tz: tzinfo) -> str:
    """'All day', '09:00–10:00', 'until 11:00' (started earlier) or 'from 22:00' (ends later)."""
    if event.all_day:
        return "All day"
    start, end = event.start.astimezone(tz), event.end.astimezone(tz)
    starts_today, ends_today = start.date() == day, end.date() == day or end == start
    if starts_today and ends_today:
        return f"{start:%H:%M}–{end:%H:%M}" if end != start else f"{start:%H:%M}"
    if starts_today:
        return f"from {start:%H:%M}"
    if ends_today and end.time() != datetime.min.time():
        return f"until {end:%H:%M}"
    return "All day"


def month_grid(year: int, month: int) -> list[list[date]]:
    """Six weeks of dates (Monday first) covering ``month``."""
    first = date(year, month, 1)
    start = first - timedelta(days=first.weekday())
    return [[start + timedelta(days=7 * week + day) for day in range(7)] for week in range(6)]


def day_label(day: date, today: date) -> str:
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return f"{day:%a} {day.day} {day:%b}"


# ----- creating events (the calendar_create tool) ---------------------------------------------
def localize(wall: datetime, tz: tzinfo) -> datetime:
    """A naive local wall time → an aware datetime. In the repeated hour when clocks go back, the
    first (summer-time) occurrence is used; a time skipped when clocks go forward moves on by
    the gap, as zoneinfo does."""
    aware = wall.replace(tzinfo=tz, fold=0)
    return aware.astimezone(UTC).astimezone(tz)


def creation_body(title: str, start: datetime, tz_name: str | None, *, end: datetime | None = None,
                  minutes: int | None = None, all_day: bool = False,
                  location: str = "") -> dict:
    """The events.insert body. ``start``/``end`` are naive local wall times (or dates for all-day
    events). A duration is real elapsed time, so across a clock change a 2-hour meeting still
    lasts two hours. Both ends carry an explicit offset and the IANA zone."""
    body: dict = {"summary": title.strip() or "(No title)"}
    if location:
        body["location"] = location
    if all_day:
        first = start.date() if isinstance(start, datetime) else start
        last = (end.date() if isinstance(end, datetime) else end) if end else first
        body["start"] = {"date": first.isoformat()}
        body["end"] = {"date": (max(last, first) + timedelta(days=1)).isoformat()}
        return body
    tz = zone(tz_name)
    begin = localize(start, tz)
    if end is not None:
        finish = localize(end, tz)
    else:
        finish = (begin.astimezone(UTC) + timedelta(minutes=minutes or 60)).astimezone(tz)
    if finish <= begin:
        raise ValueError("The event must end after it starts.")
    name = tz_name if tz_name and isinstance(tz, ZoneInfo) else None
    body["start"] = {"dateTime": begin.isoformat()}
    body["end"] = {"dateTime": finish.isoformat()}
    if name:
        body["start"]["timeZone"] = body["end"]["timeZone"] = name
    return body


def parse_local(text: str) -> datetime:
    """'2026-10-14T15:00', '2026-10-14 15:00' or '2026-10-14' (the model sends ISO local times)."""
    text = text.strip().replace(" ", "T")
    value = datetime.fromisoformat(text)
    if value.tzinfo is not None:
        raise ValueError("Give the local time without an offset, e.g. 2026-10-14T15:00.")
    return value
