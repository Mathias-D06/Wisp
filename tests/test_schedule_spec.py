from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wisp.scheduling.spec import Schedule, ScheduleError, parse_schedule

TZ = timezone(timedelta(hours=1))
NOW = datetime(2026, 10, 12, 8, 0, tzinfo=TZ)  # a Monday


def test_one_off_amazon_example():
    schedule = parse_schedule({"when": "2026-11-10T11:00"}, NOW)
    assert schedule.repeat == "none" and schedule.at == "2026-11-10T11:00+01:00"
    assert schedule.describe() == "once on Tue 10 Nov 2026 at 11:00"
    fire = schedule.trigger(TZ).get_next_fire_time(None, NOW)
    assert fire == datetime(2026, 11, 10, 11, 0, tzinfo=TZ)


def test_every_morning_at_nine():
    schedule = parse_schedule({"repeat": "daily", "time": "9:00"}, NOW)
    assert schedule.time == "09:00" and schedule.describe() == "every day at 09:00"
    fire = schedule.trigger(TZ).get_next_fire_time(None, NOW)
    assert (fire.hour, fire.minute, fire.date()) == (9, 0, NOW.date())


def test_weekdays_and_weekly():
    weekdays = parse_schedule({"repeat": "weekdays", "time": "08:30"}, NOW)
    saturday = datetime(2026, 10, 17, 9, 0, tzinfo=TZ)
    fire = weekdays.trigger(TZ).get_next_fire_time(None, saturday)
    assert fire.weekday() == 0  # skips the weekend
    weekly = parse_schedule({"repeat": "weekly", "time": "18:00", "days": ["Thursday", "mon"]},
                            NOW)
    assert weekly.days == ["mon", "thu"]
    assert weekly.describe() == "every Mon, Thu at 18:00"
    derived = parse_schedule({"repeat": "weekly", "when": "2026-10-16T07:15"}, NOW)
    assert derived.days == ["fri"] and derived.time == "07:15"


def test_monthly_and_hourly():
    monthly = parse_schedule({"repeat": "monthly", "time": "10:00", "day_of_month": 15}, NOW)
    assert monthly.trigger(TZ).get_next_fire_time(None, NOW).day == 15
    hourly = parse_schedule({"repeat": "hourly", "time": "00:30"}, NOW)
    assert hourly.describe() == "every hour at :30"
    assert hourly.trigger(TZ).get_next_fire_time(None, NOW).minute == 30


@pytest.mark.parametrize("args,message", [
    ({"when": "2026-10-11T09:00"}, "already passed"),
    ({}, "needs 'when'"),
    ({"repeat": "daily"}, "time of day"),
    ({"repeat": "daily", "time": "25:00"}, "09:30"),
    ({"repeat": "weekly", "time": "09:00", "days": ["funday"]}, "weekly task needs days"),
    ({"repeat": "monthly", "time": "09:00"}, "day_of_month"),
    ({"repeat": "yearly", "time": "09:00"}, "repeat must be"),
    ({"when": "next tuesday"}, "ISO 8601"),
])
def test_invalid(args, message):
    with pytest.raises(ScheduleError, match=message):
        parse_schedule(args, NOW)


def test_round_trip_dict():
    schedule = Schedule(repeat="weekly", time="09:00", days=["mon"])
    assert Schedule.from_dict(schedule.to_dict()) == schedule
