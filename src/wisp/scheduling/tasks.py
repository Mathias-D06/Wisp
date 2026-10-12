"""Scheduled task records: title, schedule and the resolved tool calls (steps)."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from rapidfuzz import fuzz

from wisp.db import Database
from wisp.scheduling.spec import Schedule


@dataclass
class Task:
    id: str
    title: str
    schedule: Schedule
    steps: list[dict] = field(default_factory=list)
    enabled: bool = True
    created_at: str = ""
    last_run_at: str | None = None
    last_result: str | None = None

    def as_dict(self, next_run: datetime | None = None) -> dict:
        data = {"id": self.id, "title": self.title, "schedule": self.schedule.describe(),
                "enabled": self.enabled, "steps": len(self.steps)}
        if next_run:
            data["next_run"] = next_run.isoformat(timespec="minutes")
        if self.last_result:
            data["last_result"] = self.last_result
        return data


class TaskStore:
    def __init__(self, db: Database):
        self._db = db
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    @staticmethod
    def _row(row) -> Task:
        return Task(row["id"], row["title"], Schedule.from_dict(json.loads(row["trigger"])),
                    json.loads(row["steps"]), bool(row["enabled"]), row["created_at"],
                    row["last_run_at"], row["last_result"])

    def add(self, title: str, schedule: Schedule, steps: list[dict]) -> Task:
        task_id = secrets.token_hex(4)
        self._db.execute(
            "INSERT INTO tasks(id, title, trigger, steps, enabled, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (task_id, title.strip(), json.dumps(schedule.to_dict()), json.dumps(steps),
             datetime.now().astimezone().isoformat(timespec="seconds")),
        )
        self._changed()
        return self.get(task_id)

    def get(self, task_id: str) -> Task | None:
        row = self._db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return self._row(row) if row else None

    def list(self) -> list[Task]:
        return [self._row(r) for r in self._db.query("SELECT * FROM tasks ORDER BY created_at")]

    def find(self, query: str) -> Task | None:
        task = self.get(query.strip())
        if task:
            return task
        scored = sorted(((fuzz.WRatio(query, t.title), t) for t in self.list()),
                        key=lambda pair: pair[0], reverse=True)
        return scored[0][1] if scored and scored[0][0] >= 70 else None

    def update(self, task_id: str, *, title: str | None = None, schedule: Schedule | None = None,
               enabled: bool | None = None, steps: list[dict] | None = None) -> Task:
        task = self.get(task_id)
        if task is None:
            raise ValueError("No such task.")
        self._db.execute(
            "UPDATE tasks SET title = ?, trigger = ?, enabled = ?, steps = ? WHERE id = ?",
            ((title or task.title).strip(), json.dumps((schedule or task.schedule).to_dict()),
             int(task.enabled if enabled is None else enabled),
             json.dumps(task.steps if steps is None else steps), task_id),
        )
        self._changed()
        return self.get(task_id)

    def delete(self, task_id: str) -> None:
        self._db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._changed()

    def record_run(self, task_id: str, result: str) -> None:
        self._db.execute(
            "UPDATE tasks SET last_run_at = ?, last_result = ? WHERE id = ?",
            (datetime.now().astimezone().isoformat(timespec="seconds"), result[:500], task_id),
        )
        self._changed()
