"""Usage stats: words dictated, time saved, commands run, routines executed.

Time saved per dictation = time to type the words at the user's typing speed (Settings →
General, default 40 words per minute) minus the time spent speaking. Never negative.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from wisp.db import Database

KINDS = ("dictation", "command", "routine")


@dataclass
class StatsSummary:
    label: str
    words: int
    seconds_saved: float
    commands: int
    routines: int
    dictations: int


def time_saved_seconds(words: int, speaking_seconds: float, typing_wpm: int) -> float:
    typing_seconds = words / max(typing_wpm, 1) * 60
    return max(0.0, typing_seconds - speaking_seconds)


class Stats:
    def __init__(self, db: Database, typing_wpm: Callable[[], int],
                 now: Callable[[], datetime] = lambda: datetime.now().astimezone()):
        self._db = db
        self._wpm = typing_wpm
        self._now = now
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def record(self, kind: str, words: int = 0, seconds: float = 0.0) -> None:
        if kind not in KINDS:
            raise ValueError(f"Unknown stats kind {kind}")
        now = self._now()
        self._db.execute(
            "INSERT INTO stats_events(ts, day, kind, words, seconds) VALUES (?, ?, ?, ?, ?)",
            (now.isoformat(timespec="seconds"), now.date().isoformat(), kind, words, seconds),
        )
        for listener in list(self._listeners):
            listener()

    def _summary(self, label: str, start: date, end: date) -> StatsSummary:
        rows = self._db.query(
            "SELECT kind, COUNT(*) AS n, SUM(words) AS w, SUM(seconds) AS s FROM stats_events "
            "WHERE day >= ? AND day <= ? GROUP BY kind",
            (start.isoformat(), end.isoformat()),
        )
        by_kind = {r["kind"]: r for r in rows}
        dictation = by_kind.get("dictation")
        words = int(dictation["w"] or 0) if dictation else 0
        wpm = self._wpm()
        saved = sum(
            time_saved_seconds(int(r["words"]), float(r["seconds"]), wpm)
            for r in self._db.query(
                "SELECT words, seconds FROM stats_events "
                "WHERE kind = 'dictation' AND day >= ? AND day <= ?",
                (start.isoformat(), end.isoformat()),
            )
        )
        return StatsSummary(
            label=label,
            words=words,
            seconds_saved=saved,
            commands=int(by_kind["command"]["n"]) if "command" in by_kind else 0,
            routines=int(by_kind["routine"]["n"]) if "routine" in by_kind else 0,
            dictations=int(dictation["n"]) if dictation else 0,
        )

    def today(self) -> StatsSummary:
        today = self._now().date()
        return self._summary("Today", today, today)

    def this_week(self) -> StatsSummary:
        today = self._now().date()
        monday = today - timedelta(days=today.weekday())
        return self._summary("This week", monday, today)

    def daily(self, days: int = 7) -> list[StatsSummary]:
        today = self._now().date()
        result = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            result.append(self._summary(day.strftime("%a"), day, day))
        return result
