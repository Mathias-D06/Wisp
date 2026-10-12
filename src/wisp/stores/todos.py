"""To-do list with optional due time and reminder."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from rapidfuzz import fuzz

from wisp.db import Database


@dataclass
class Todo:
    id: int
    text: str
    done: bool
    due_at: datetime | None
    remind: bool
    reminded: bool
    created_at: str

    def as_dict(self) -> dict:
        data: dict = {"id": self.id, "text": self.text}
        if self.due_at:
            data["due"] = self.due_at.isoformat(timespec="minutes")
        if self.done:
            data["done"] = True
        return data


def _now() -> datetime:
    return datetime.now().astimezone()


class TodoStore:
    def __init__(self, db: Database, now: Callable[[], datetime] = _now):
        self._db = db
        self._now = now
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    @staticmethod
    def _row(row) -> Todo:
        due = datetime.fromisoformat(row["due_at"]) if row["due_at"] else None
        return Todo(row["id"], row["text"], bool(row["done"]), due, bool(row["remind"]),
                    bool(row["reminded"]), row["created_at"])

    def add(self, text: str, due_at: datetime | None = None, remind: bool | None = None) -> Todo:
        text = text.strip()
        if not text:
            raise ValueError("A to-do needs some text.")
        remind = bool(due_at) if remind is None else (remind and due_at is not None)
        todo_id = self._db.execute(
            "INSERT INTO todos(text, due_at, remind, created_at) VALUES (?, ?, ?, ?)",
            (text, due_at.isoformat() if due_at else None, int(remind),
             self._now().isoformat(timespec="seconds")),
        )
        self._changed()
        return self.get(todo_id)

    def get(self, todo_id: int) -> Todo | None:
        row = self._db.query_one("SELECT * FROM todos WHERE id = ?", (todo_id,))
        return self._row(row) if row else None

    def list(self, include_done: bool = False, limit: int = 100) -> list[Todo]:
        where = "" if include_done else "WHERE done = 0"
        rows = self._db.query(
            f"SELECT * FROM todos {where} ORDER BY done, due_at IS NULL, due_at, id LIMIT ?",
            (limit,),
        )
        return [self._row(r) for r in rows]

    def find(self, query: str) -> Todo | None:
        """Best open to-do matching ``query`` (an id or words from its text)."""
        if query.strip().isdigit():
            todo = self.get(int(query.strip()))
            if todo:
                return todo
        scored = [(fuzz.WRatio(query, t.text), t) for t in self.list()]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0][1] if scored and scored[0][0] >= 70 else None

    def set_done(self, todo_id: int, done: bool = True) -> None:
        self._db.execute(
            "UPDATE todos SET done = ?, completed_at = ? WHERE id = ?",
            (int(done), self._now().isoformat(timespec="seconds") if done else None, todo_id),
        )
        self._changed()

    def update(self, todo_id: int, text: str | None = None, due_at: datetime | None = None,
               clear_due: bool = False) -> None:
        todo = self.get(todo_id)
        if todo is None:
            raise ValueError("No such to-do.")
        new_due = None if clear_due else (due_at or todo.due_at)
        self._db.execute(
            "UPDATE todos SET text = ?, due_at = ?, remind = ?, reminded = 0 WHERE id = ?",
            ((text or todo.text).strip(), new_due.isoformat() if new_due else None,
             int(new_due is not None), todo_id),
        )
        self._changed()

    def delete(self, todo_id: int) -> None:
        self._db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self._changed()

    def due_reminders(self) -> list[Todo]:
        now = self._now()
        return [t for t in self.list() if t.remind and not t.reminded and t.due_at
                and t.due_at <= now]

    def mark_reminded(self, todo_id: int) -> None:
        self._db.execute("UPDATE todos SET reminded = 1 WHERE id = ?", (todo_id,))

    def due_today(self) -> list[Todo]:
        today = self._now().date()
        return [t for t in self.list() if t.due_at and t.due_at.date() <= today]
