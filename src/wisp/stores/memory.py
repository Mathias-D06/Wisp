"""Long-term memory: short facts the user asked Wisp to remember (SQLite + FTS5).

Search ranks with FTS5 ``bm25()`` (proven by ``spikes/sqlite_fts5.py``). At session start only
a few facts are injected (``session_facts``): pinned first, then the most often recalled, then
the most recently used or changed, within a character budget (DECISIONS.md D-032). Everything
else stays reachable through the ``recall`` tool.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from wisp.db import Database

MAX_TEXT = 300
MAX_MEMORIES = 1000
SESSION_FACTS = 8
SESSION_CHARS = 1000


def _now() -> datetime:
    return datetime.now().astimezone()


def _normal(text: str) -> str:
    return " ".join(text.split()).casefold()


def fts_query(text: str) -> str:
    """Words of ``text`` as an FTS5 OR query of quoted prefix terms (no FTS syntax leaks in)."""
    words = [w for w in re.findall(r"\w+", text.casefold()) if len(w) > 1]
    return " OR ".join(f'"{w}"*' for w in dict.fromkeys(words))


@dataclass
class Memory:
    id: int
    text: str
    pinned: bool
    use_count: int
    created_at: str
    updated_at: str
    last_used_at: str | None

    def as_dict(self) -> dict:
        return {"id": self.id, "fact": self.text, "pinned": self.pinned}


class MemoryStore:
    def __init__(self, db: Database, now: Callable[[], datetime] = _now):
        self._db = db
        self._now = now
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    def _stamp(self) -> str:
        return self._now().isoformat(timespec="seconds")

    @staticmethod
    def _clean(text: str) -> str:
        text = " ".join((text or "").split())
        if not text:
            raise ValueError("A memory can't be empty.")
        if len(text) > MAX_TEXT:
            raise ValueError(f"Keep memories under {MAX_TEXT} characters.")
        return text

    @staticmethod
    def _row(row) -> Memory:
        return Memory(row["id"], row["text"], bool(row["pinned"]), row["use_count"],
                      row["created_at"], row["updated_at"], row["last_used_at"])

    # ----- writes ------------------------------------------------------------------------------
    def add(self, text: str, pinned: bool = False) -> Memory:
        """Store a fact; an identical fact (ignoring case and spacing) is refreshed instead."""
        text = self._clean(text)
        for existing in self.all():
            if _normal(existing.text) == _normal(text):
                self.update(existing.id, pinned=existing.pinned or pinned)
                return self.get(existing.id)
        if self.count() >= MAX_MEMORIES:
            raise ValueError(f"Memory is full ({MAX_MEMORIES} facts). Delete some in Settings.")
        stamp = self._stamp()
        memory_id = self._db.execute(
            "INSERT INTO memories(text, pinned, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (text, int(pinned), stamp, stamp))
        self._changed()
        return self.get(memory_id)

    def update(self, memory_id: int, text: str | None = None,
               pinned: bool | None = None) -> None:
        current = self.get(memory_id)
        if current is None:
            raise KeyError(memory_id)
        new_text = self._clean(text) if text is not None else current.text
        new_pinned = current.pinned if pinned is None else pinned
        self._db.execute("UPDATE memories SET text = ?, pinned = ?, updated_at = ? WHERE id = ?",
                         (new_text, int(new_pinned), self._stamp(), memory_id))
        self._changed()

    def delete(self, memory_id: int) -> None:
        self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._changed()

    def clear(self) -> None:
        self._db.execute("DELETE FROM memories")
        self._changed()

    def mark_used(self, ids: list[int]) -> None:
        if not ids:
            return
        stamp = self._stamp()
        with self._db.transaction() as conn:
            conn.executemany("UPDATE memories SET use_count = use_count + 1, last_used_at = ? "
                             "WHERE id = ?", [(stamp, i) for i in ids])

    # ----- reads -------------------------------------------------------------------------------
    def get(self, memory_id: int) -> Memory | None:
        row = self._db.query_one("SELECT * FROM memories WHERE id = ?", (memory_id,))
        return self._row(row) if row else None

    def count(self) -> int:
        return int(self._db.query_one("SELECT COUNT(*) AS n FROM memories")["n"])

    def all(self) -> list[Memory]:
        rows = self._db.query("SELECT * FROM memories ORDER BY pinned DESC, id DESC")
        return [self._row(r) for r in rows]

    def search(self, text: str, limit: int = 5) -> list[Memory]:
        query = fts_query(text)
        if not query:
            return []
        rows = self._db.query(
            "SELECT m.* FROM memories_fts JOIN memories m ON m.id = memories_fts.rowid "
            "WHERE memories_fts MATCH ? ORDER BY bm25(memories_fts), m.pinned DESC LIMIT ?",
            (query, limit))
        return [self._row(r) for r in rows]

    def find(self, text: str) -> Memory | None:
        """A memory by id or by the best full-text match."""
        if text.strip().isdigit():
            return self.get(int(text.strip()))
        matches = self.search(text, 1)
        return matches[0] if matches else None

    def session_facts(self, limit: int = SESSION_FACTS, budget: int = SESSION_CHARS) -> list[str]:
        rows = self._db.query(
            "SELECT * FROM memories ORDER BY pinned DESC, use_count DESC, "
            "COALESCE(last_used_at, updated_at) DESC, id DESC LIMIT ?", (limit,))
        facts, used = [], 0
        for row in rows:
            if used + len(row["text"]) > budget:
                break
            facts.append(row["text"])
            used += len(row["text"])
        return facts
