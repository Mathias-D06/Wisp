"""Action log: every tool call with time, tool, arguments, decision and result."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from wisp.db import Database

MAX_FIELD = 2000


def _compact(value: Any, redact: Callable[[str], str] | None) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if redact:
        text = redact(text)
    if len(text) > MAX_FIELD:
        text = text[: MAX_FIELD - 1] + "…"
    return text


@dataclass
class LogEntry:
    id: int
    ts: str
    origin: str
    tool: str
    args: str
    decision: str
    result: str
    ok: bool
    duration_ms: int


class ActionLog:
    def __init__(self, db: Database, redact: Callable[[str], str] | None = None):
        self._db = db
        self._redact = redact
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def record(self, *, origin: str, tool: str, args: dict[str, Any], decision: str,
               result: Any, ok: bool, duration_ms: int = 0) -> int:
        row_id = self._db.execute(
            "INSERT INTO action_log(ts, origin, tool, args, decision, result, ok, duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().astimezone().isoformat(timespec="seconds"),
                origin,
                tool,
                _compact(args, self._redact),
                decision,
                _compact(result, self._redact),
                int(ok),
                duration_ms,
            ),
        )
        for listener in list(self._listeners):
            listener()
        return row_id

    def recent(self, limit: int = 300) -> list[LogEntry]:
        rows = self._db.query(
            "SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [
            LogEntry(r["id"], r["ts"], r["origin"], r["tool"], r["args"], r["decision"],
                     r["result"], bool(r["ok"]), r["duration_ms"])
            for r in rows
        ]

    def clear(self) -> None:
        self._db.execute("DELETE FROM action_log")
