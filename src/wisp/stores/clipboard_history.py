"""Clipboard history: the last N text and image items (SQLite)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from wisp.db import Database

MAX_TEXT = 100_000
MAX_IMAGE = 8 * 1024 * 1024


@dataclass
class ClipItem:
    id: int
    kind: str  # "text" | "image"
    text: str | None
    image: bytes | None
    created_at: str

    @property
    def preview(self) -> str:
        if self.kind == "image":
            return "Image"
        return " ".join((self.text or "").split())[:200]


class ClipboardHistory:
    def __init__(self, db: Database, max_items: Callable[[], int]):
        self._db = db
        self._max_items = max_items
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    def _store(self, kind: str, text: str | None, image: bytes | None, digest: str) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM clipboard_items WHERE digest = ?", (digest,))
            conn.execute("INSERT INTO clipboard_items(kind, text, image, digest, created_at) "
                         "VALUES (?, ?, ?, ?, ?)", (kind, text, image, digest, now))
            keep = max(1, self._max_items())
            conn.execute("DELETE FROM clipboard_items WHERE id NOT IN (SELECT id FROM "
                         "clipboard_items ORDER BY id DESC LIMIT ?)", (keep,))
        self._changed()

    def add_text(self, text: str) -> bool:
        if not text or not text.strip() or len(text) > MAX_TEXT:
            return False
        self._store("text", text, None, "t:" + hashlib.sha256(text.encode()).hexdigest())
        return True

    def add_image(self, png: bytes) -> bool:
        if not png or len(png) > MAX_IMAGE:
            return False
        self._store("image", None, png, "i:" + hashlib.sha256(png).hexdigest())
        return True

    @staticmethod
    def _row(row) -> ClipItem:
        return ClipItem(row["id"], row["kind"], row["text"], row["image"], row["created_at"])

    def items(self, search: str = "", limit: int = 200) -> list[ClipItem]:
        if search:
            rows = self._db.query(
                "SELECT * FROM clipboard_items WHERE kind = 'text' AND text LIKE ? "
                "ORDER BY id DESC LIMIT ?", (f"%{search}%", limit))
        else:
            rows = self._db.query("SELECT * FROM clipboard_items ORDER BY id DESC LIMIT ?",
                                  (limit,))
        return [self._row(r) for r in rows]

    def get(self, item_id: int) -> ClipItem | None:
        row = self._db.query_one("SELECT * FROM clipboard_items WHERE id = ?", (item_id,))
        return self._row(row) if row else None

    def delete(self, item_id: int) -> None:
        self._db.execute("DELETE FROM clipboard_items WHERE id = ?", (item_id,))
        self._changed()

    def clear(self) -> None:
        self._db.execute("DELETE FROM clipboard_items")
        self._changed()
