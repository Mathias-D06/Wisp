"""F10 stats: words dictated, time saved, commands, routines — per day and per week."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wisp.stores.stats import Stats, time_saved_seconds

TZ = timezone(timedelta(hours=1))


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 14, 10, 0, tzinfo=TZ)  # a Wednesday

    def __call__(self):
        return self.now


@pytest.fixture
def stats(db):
    clock = Clock()
    wpm = {"value": 40}
    store = Stats(db, lambda: wpm["value"], clock)
    store.clock, store.wpm = clock, wpm
    return store


def test_time_saved_formula():
    assert time_saved_seconds(400, 60, 40) == 540  # 10 min typing − 1 min speaking
    assert time_saved_seconds(10, 120, 40) == 0  # never negative
    assert time_saved_seconds(10, 0, 0) == 600  # guards a zero typing speed


def test_today_and_week_boundaries(stats):
    clock = stats.clock
    clock.now -= timedelta(days=2)  # Monday: same week
    stats.record("dictation", words=200, seconds=30)
    clock.now -= timedelta(days=1)  # Sunday: previous week
    stats.record("dictation", words=999, seconds=10)
    stats.record("command")
    clock.now += timedelta(days=3)  # back to Wednesday
    stats.record("dictation", words=100, seconds=60)
    stats.record("command")
    stats.record("command")
    stats.record("routine")
    today, week = stats.today(), stats.this_week()
    assert (today.words, today.commands, today.routines, today.dictations) == (100, 2, 1, 1)
    assert today.seconds_saved == pytest.approx(150 - 60)
    assert (week.words, week.commands, week.dictations) == (300, 2, 2)
    assert week.seconds_saved == pytest.approx((300 - 30) + (150 - 60))


def test_time_saved_uses_current_typing_speed(stats):
    stats.record("dictation", words=120, seconds=0)
    assert stats.today().seconds_saved == pytest.approx(180)
    stats.wpm["value"] = 60
    assert stats.today().seconds_saved == pytest.approx(120)


def test_daily_series(stats):
    stats.clock.now -= timedelta(days=1)
    stats.record("dictation", words=50, seconds=5)
    stats.clock.now += timedelta(days=1)
    stats.record("command")
    days = stats.daily(7)
    assert [d.label for d in days] == ["Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"]
    assert days[-2].words == 50 and days[-1].commands == 1
    assert sum(d.words for d in days[:-2]) == 0


def test_unknown_kind_and_listener(stats):
    calls = []
    stats.subscribe(lambda: calls.append(1))
    stats.record("routine")
    assert calls == [1]
    with pytest.raises(ValueError):
        stats.record("nap")
