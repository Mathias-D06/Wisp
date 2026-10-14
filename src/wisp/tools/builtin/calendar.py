"""Google Calendar tools (skill group "calendar", D-050): what's on, and adding an event.

calendar_list reads the offline cache (synced every 5 minutes), so it answers even without a
connection. calendar_create is confirm-tier: a card shows the title, time and calendar before
anything is saved. Times are local wall times in the primary calendar's zone (Europe/London and
its daylight saving, for example).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from wisp.gcal.google import CalendarError
from wisp.gcal.times import agenda, creation_body, localize, parse_local, span_text
from wisp.tools.base import Risk, Tool, ToolContext, ToolError, boolean, integer, obj, string

MAX_DAYS = 31


def _service(ctx: ToolContext):
    service = getattr(ctx.services, "calendar", None)
    if service is None or not service.connected:
        raise ToolError("Google Calendar isn't connected. Connect it in Settings → Accounts.")
    return service


def _day(text: str | None, today: date) -> date:
    if not text:
        return today
    word = text.strip().lower()
    if word == "today":
        return today
    if word == "tomorrow":
        return today + timedelta(days=1)
    try:
        return parse_local(text).date()
    except ValueError as exc:
        raise ToolError("Give dates as YYYY-MM-DD (call get_current_time first).") from exc


def calendar_list(ctx: ToolContext, args: dict) -> dict:
    service = _service(ctx)
    tz = service.tz()
    today = datetime.now(tz).date()
    first = _day(args.get("start"), today)
    days = max(1, min(MAX_DAYS, int(args.get("days") or 1)))
    start = localize(datetime.combine(first, datetime.min.time()), tz)
    end = localize(datetime.combine(first + timedelta(days=days), datetime.min.time()), tz)
    grouped = agenda(service.events(start, end), first, days, tz)
    result = {"days": [{"date": day.isoformat(),
                        "events": [{"title": e.title, "time": span_text(e, day, tz),
                                    **({"location": e.location} if e.location else {})}
                                   for e in events]} for day, events in grouped],
              "time_zone": str(tz)}
    last = service.store.last_synced()
    if last is not None:
        result["last_synced"] = last.astimezone(tz).isoformat(timespec="minutes")
    if service.state() in ("reconnect", "error"):
        result["note"] = service.error
    return result


def _body(ctx: ToolContext, args: dict) -> tuple[dict, dict]:
    service = _service(ctx)
    try:
        calendar = service.writable_calendar(args.get("calendar"))
        start = parse_local(args["start"])
        end = parse_local(args["end"]) if args.get("end") else None
        body = creation_body(args["title"], start, service.time_zone(), end=end,
                             minutes=args.get("minutes"), all_day=bool(args.get("all_day")),
                             location=args.get("location") or "")
    except (CalendarError, ValueError) as exc:
        raise ToolError(str(exc)) from exc
    return calendar, body


def calendar_create(ctx: ToolContext, args: dict) -> dict:
    calendar, body = _body(ctx, args)
    try:
        event = _service(ctx).create(calendar["id"], body)
    except CalendarError as exc:
        raise ToolError(str(exc)) from exc
    return {"created": event.title, "calendar": calendar["title"], "link": event.link}


def describe_create(args: dict) -> str:
    """What the confirmation card shows: title, time and calendar."""
    title = args.get("title") or "(No title)"
    when = args.get("start", "")
    try:
        start = parse_local(when)
        if args.get("all_day"):
            when = f"{start:%a %d %b} (all day)"
        elif args.get("end"):
            when = f"{start:%a %d %b %H:%M}–{parse_local(args['end']):%H:%M}"
        else:
            finish = start + timedelta(minutes=int(args.get("minutes") or 60))
            when = f"{start:%a %d %b %H:%M}–{finish:%H:%M}"
    except (ValueError, TypeError):
        pass
    return f"add “{title}” to {args.get('calendar') or 'your main calendar'}, {when}"


def tools() -> list[Tool]:
    return [
        Tool("calendar_list", "What's on the user's Google Calendar: events for a day or a few "
             "days, with times in their time zone.",
             obj({"start": string("First day: 'today', 'tomorrow' or YYYY-MM-DD (default today)"),
                  "days": integer("How many days (1-31, default 1)")}),
             calendar_list, "calendar"),
        Tool("calendar_create", "Add an event to the user's Google Calendar (they confirm on a "
             "card first). Times are local, without an offset.",
             obj({"title": string("What the event is"),
                  "start": string("Local start, YYYY-MM-DDTHH:MM (or YYYY-MM-DD if all day)"),
                  "end": string("Optional local end, YYYY-MM-DDTHH:MM"),
                  "minutes": integer("Optional length in minutes when no end (default 60)"),
                  "all_day": boolean("An all-day event"),
                  "calendar": string("Optional calendar name (default: the main one)"),
                  "location": string("Optional place")},
                 ["title", "start"]),
             calendar_create, "calendar", risk=Risk.CONFIRM, summary=describe_create,
             schedulable=False),
    ]
