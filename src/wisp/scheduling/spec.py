"""Schedules: parsing the model's structured request, triggers, and plain-English descriptions.

APScheduler 3.x CronTrigger: day_of_week 0/mon = Monday; DateTrigger for one-off runs
(apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, tzinfo

REPEATS = ["none", "daily", "weekdays", "weekly", "monthly", "hourly"]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_LABELS = dict(zip(DAYS, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], strict=True))


class ScheduleError(ValueError):
    pass


@dataclass
class Schedule:
    repeat: str = "none"
    at: str | None = None  # ISO 8601 with offset, for one-off runs
    time: str | None = None  # "HH:MM" for repeating runs
    days: list[str] = field(default_factory=list)  # weekly
    day_of_month: int | None = None  # monthly

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Schedule:
        return cls(**{k: data.get(k) for k in ("repeat", "at", "time", "day_of_month")},
                   days=list(data.get("days") or []))

    @property
    def one_off(self) -> bool:
        return self.repeat == "none"

    def hour_minute(self) -> tuple[int, int]:
        hour, minute = (self.time or "00:00").split(":")
        return int(hour), int(minute)

    def trigger(self, tz: tzinfo):
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger

        if self.one_off:
            return DateTrigger(run_date=datetime.fromisoformat(self.at), timezone=tz)
        hour, minute = self.hour_minute()
        if self.repeat == "daily":
            return CronTrigger(hour=hour, minute=minute, timezone=tz)
        if self.repeat == "weekdays":
            return CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=tz)
        if self.repeat == "weekly":
            return CronTrigger(day_of_week=",".join(self.days), hour=hour, minute=minute,
                               timezone=tz)
        if self.repeat == "monthly":
            return CronTrigger(day=self.day_of_month, hour=hour, minute=minute, timezone=tz)
        return CronTrigger(minute=minute, timezone=tz)  # hourly

    def describe(self) -> str:
        if self.one_off:
            when = datetime.fromisoformat(self.at)
            return f"once on {when.strftime('%a %d %b %Y')} at {when.strftime('%H:%M')}"
        if self.repeat == "daily":
            return f"every day at {self.time}"
        if self.repeat == "weekdays":
            return f"weekdays at {self.time}"
        if self.repeat == "weekly":
            return f"every {', '.join(DAY_LABELS[d] for d in self.days)} at {self.time}"
        if self.repeat == "monthly":
            return f"monthly on day {self.day_of_month} at {self.time}"
        return f"every hour at :{self.time.split(':')[1]}"


_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_when(text: str, tz: tzinfo) -> datetime:
    try:
        value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScheduleError(f"'{text}' is not an ISO 8601 date and time.") from exc
    return value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)


def parse_schedule(args: dict, now: datetime) -> Schedule:
    """Validate the schedule fields of a schedule_task/update call (``now`` is tz-aware)."""
    tz = now.tzinfo
    repeat = (args.get("repeat") or "none").lower()
    if repeat not in REPEATS:
        raise ScheduleError(f"repeat must be one of {', '.join(REPEATS)}.")
    when = parse_when(args["when"], tz) if args.get("when") else None
    time_text = args.get("time")
    if time_text:
        match = _TIME.match(time_text.strip())
        if not match:
            raise ScheduleError("time must look like 09:30.")
        time_text = f"{int(match.group(1)):02d}:{match.group(2)}"
    elif when is not None:
        time_text = when.strftime("%H:%M")

    if repeat == "none":
        if when is None:
            raise ScheduleError("A one-off task needs 'when' (ISO 8601 local date and time).")
        if (when - now).total_seconds() < -60:
            raise ScheduleError(f"{when.strftime('%d %b %H:%M')} has already passed.")
        return Schedule(repeat="none", at=when.isoformat(timespec="minutes"))
    if not time_text:
        raise ScheduleError("A repeating task needs a time of day (time=HH:MM).")
    if repeat == "weekly":
        days = [d.lower()[:3] for d in (args.get("days") or [])]
        if not days and when is not None:
            days = [DAYS[when.weekday()]]
        bad = [d for d in days if d not in DAYS]
        if not days or bad:
            raise ScheduleError("A weekly task needs days such as ['mon', 'thu'].")
        ordered = [d for d in DAYS if d in days]
        return Schedule(repeat="weekly", time=time_text, days=ordered)
    if repeat == "monthly":
        dom = args.get("day_of_month") or (when.day if when else None)
        if not dom or not 1 <= int(dom) <= 31:
            raise ScheduleError("A monthly task needs day_of_month (1-31).")
        return Schedule(repeat="monthly", time=time_text, day_of_month=int(dom))
    return Schedule(repeat=repeat, time=time_text)
