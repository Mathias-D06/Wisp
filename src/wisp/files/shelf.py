"""The shelf (D-051): files parked on the island to drag somewhere else later.

The shelf holds references, never copies: a parked file stays where it is, and moving or
deleting it in Explorer shows it as missing on the shelf. Kept in SQLite, so it survives
restarts. Folders can be parked too.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS shelf (
        path TEXT PRIMARY KEY COLLATE NOCASE,
        added_at REAL NOT NULL)""",
)
MAX_ITEMS = 50


@dataclass(frozen=True)
class ShelfItem:
    path: Path
    added_at: float

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def name(self) -> str:
        return self.path.name or str(self.path)


class Shelf:
    def __init__(self, db, clock: Callable[[], float] = time.time) -> None:
        self.db = db
        self.clock = clock
        self._listeners: list[Callable[[], None]] = []
        with db.transaction() as conn:
            for statement in SCHEMA:
                conn.execute(statement)

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    def add(self, paths: Iterable[Path | str]) -> list[Path]:
        """Park files or folders (newest first). Returns those added; missing paths are
        skipped. Parking something already on the shelf moves it to the front."""
        added = []
        now = self.clock()
        with self.db.transaction() as conn:
            for index, raw in enumerate(paths):
                path = Path(os.path.abspath(str(raw)))
                if not path.exists():
                    continue
                conn.execute("INSERT OR REPLACE INTO shelf(path, added_at) VALUES (?, ?)",
                             (str(path), now + index * 1e-3))
                added.append(path)
            conn.execute("DELETE FROM shelf WHERE path NOT IN (SELECT path FROM shelf "
                         "ORDER BY added_at DESC LIMIT ?)", (MAX_ITEMS,))
        if added:
            self._changed()
        return added

    def remove(self, path: Path | str) -> bool:
        removed = self.db.execute("DELETE FROM shelf WHERE path = ?",
                                  (str(Path(os.path.abspath(str(path)))),)) > 0
        if removed:
            self._changed()
        return removed

    def clear(self) -> None:
        self.db.execute("DELETE FROM shelf")
        self._changed()

    def items(self) -> list[ShelfItem]:
        rows = self.db.query("SELECT path, added_at FROM shelf ORDER BY added_at DESC")
        return [ShelfItem(Path(row["path"]), row["added_at"]) for row in rows]

    def newest(self) -> ShelfItem | None:
        return next((item for item in self.items() if item.exists), None)

    def forget_missing(self) -> int:
        missing = [item.path for item in self.items() if not item.exists]
        for path in missing:
            self.db.execute("DELETE FROM shelf WHERE path = ?", (str(path),))
        if missing:
            self._changed()
        return len(missing)

    def renamed(self, old: Path, new: Path) -> None:
        """Keep a parked file on the shelf when Wisp renames or moves it."""
        if self.db.execute("UPDATE shelf SET path = ? WHERE path = ?", (str(new), str(old))):
            self._changed()
