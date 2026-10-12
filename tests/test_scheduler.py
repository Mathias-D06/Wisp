"""Real APScheduler + SQLite job store: persistence, runs, missed-run policy."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from tests.fakes import until  # noqa: F401  (shared helper style)
from wisp.scheduling.scheduler import TaskScheduler
from wisp.scheduling.spec import Schedule
from wisp.scheduling.tasks import TaskStore
from wisp.settings import Settings


class Harness:
    def __init__(self, db, tmp_path, grace_hours=12):
        self.settings = Settings()
        self.settings.scheduler.one_off_grace_hours = grace_hours
        self.store = TaskStore(db)
        self.url = f"sqlite:///{tmp_path / 'jobs.sqlite3'}"
        self.ran: list[str] = []
        self.notes: list[tuple[str, str]] = []

    def make(self) -> TaskScheduler:
        return TaskScheduler(self.store, self.url, lambda: self.settings, self.execute,
                             lambda title, body: self.notes.append((title, body)))

    def execute(self, task):
        self.ran.append(task.title)
        return True, "✓ open Spotify"


def wait_for(condition, timeout=6.0):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        time.sleep(0.05)


def soon(seconds: float) -> str:
    return (datetime.now().astimezone() + timedelta(seconds=seconds)).isoformat()


def test_one_off_runs_notifies_and_disables(db, tmp_path):
    h = Harness(db, tmp_path)
    scheduler = h.make()
    scheduler.start()
    try:
        task = h.store.add("Open Spotify", Schedule(repeat="none", at=soon(1)), [])
        scheduler.schedule(task)
        assert scheduler.next_run(task.id) is not None
        wait_for(lambda: h.ran == ["Open Spotify"])
        wait_for(lambda: not h.store.get(task.id).enabled)
        assert h.notes[0][0] == "Routine done: Open Spotify"
        assert h.store.get(task.id).last_result == "✓ open Spotify"
    finally:
        scheduler.shutdown()


def test_job_persists_and_runs_late_after_restart(db, tmp_path):
    h = Harness(db, tmp_path)
    first = h.make()
    first.start()
    task = h.store.add("Late but fine", Schedule(repeat="none", at=soon(1)), [])
    first.schedule(task)
    first.shutdown()  # app closed before the run time
    time.sleep(2.2)
    second = h.make()
    second.start()
    try:
        wait_for(lambda: h.ran == ["Late but fine"])
    finally:
        second.shutdown()


def test_missed_beyond_grace_is_reported(db, tmp_path):
    h = Harness(db, tmp_path, grace_hours=0)
    first = h.make()
    first.start()
    task = h.store.add("Too late", Schedule(repeat="none", at=soon(1)), [])
    first.schedule(task)
    first.shutdown()
    time.sleep(2.2)
    second = h.make()
    second.start()
    try:
        wait_for(lambda: h.notes)
        assert h.ran == []
        assert h.notes[0][0] == "Missed while Wisp was closed"
        assert h.store.get(task.id).last_result.startswith("Missed")
        assert not h.store.get(task.id).enabled
    finally:
        second.shutdown()


def test_recurring_next_run_unschedule_and_sync(db, tmp_path):
    h = Harness(db, tmp_path)
    scheduler = h.make()
    scheduler.start()
    task = h.store.add("Morning", Schedule(repeat="daily", time="09:00"), [])
    scheduler.schedule(task)
    next_run = scheduler.next_run(task.id)
    assert (next_run.hour, next_run.minute) == (9, 0)
    assert [t.title for t, _ in scheduler.upcoming()] == ["Morning"]
    scheduler.unschedule(task.id)
    assert scheduler.next_run(task.id) is None
    scheduler.shutdown()
    # The task row still exists and is enabled: a restart re-creates the missing job.
    again = h.make()
    again.start()
    try:
        assert again.next_run(task.id) is not None
    finally:
        again.shutdown()


@pytest.mark.parametrize("repeat,grace", [("none", 12 * 3600), ("daily", 3600)])
def test_grace_policy(db, tmp_path, repeat, grace):
    h = Harness(db, tmp_path)
    schedule = Schedule(repeat=repeat, at=soon(3600) if repeat == "none" else None,
                        time="09:00" if repeat != "none" else None)
    task = h.store.add("x", schedule, [])
    assert h.make().grace_seconds(task) == grace
