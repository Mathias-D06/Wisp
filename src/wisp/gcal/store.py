"""The calendar's offline cache in SQLite (D-050): calendars (with colour, zone and whether the
user shows them), events, and each calendar's sync token. Merging follows Google's sync guide:
an incremental page holds changed events, and deleted ones arrive with status "cancelled";
a 410 means the token is no longer valid, so the calendar's events are wiped before a full sync.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from wisp.gcal.times import Event, event_from_item

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS gcal_calendars (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, color TEXT NOT NULL, is_primary INTEGER NOT NULL,
        access_role TEXT NOT NULL, time_zone TEXT, shown INTEGER NOT NULL,
        sync_token TEXT, full_sync_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS gcal_events (
        calendar_id TEXT NOT NULL, id TEXT NOT NULL, title TEXT NOT NULL, all_day INTEGER NOT NULL,
        start_utc TEXT, end_utc TEXT, start_date TEXT, end_date TEXT, link TEXT, location TEXT,
        PRIMARY KEY (calendar_id, id))""",
    """CREATE INDEX IF NOT EXISTS gcal_events_start ON gcal_events(start_utc)""",
]
READABLE = ("reader", "writer", "writerWithoutPrivateAccess", "owner")  # freeBusyReader: no events
# calendar.events.owned lets Wisp "create, change, and delete events on calendars you own"
# (D-050): not on calendars merely shared with write access.
OWNED = ("owner",)


class CalendarStore:
    def __init__(self, db):
        self.db = db
        with db.transaction() as conn:
            for statement in SCHEMA:
                conn.execute(statement)

    # ----- calendars ---------------------------------------------------------------------------
    def set_calendars(self, items: list[dict]) -> None:
        """Replace the calendar list, keeping each known calendar's shown choice and token. New
        calendars are shown when Google shows them (``selected``) or they are the primary one."""
        known = {row["id"]: row for row in self.db.query("SELECT * FROM gcal_calendars")}
        keep = []
        with self.db.transaction() as conn:
            for item in items:
                if item.get("deleted") or item.get("accessRole") not in READABLE:
                    continue
                cid = item["id"]
                keep.append(cid)
                old = known.get(cid)
                shown = old["shown"] if old else int(bool(item.get("selected")
                                                          or item.get("primary")))
                conn.execute(
                    """INSERT INTO gcal_calendars(id, title, color, is_primary, access_role,
                           time_zone, shown, sync_token, full_sync_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET title=excluded.title, color=excluded.color,
                           is_primary=excluded.is_primary, access_role=excluded.access_role,
                           time_zone=excluded.time_zone""",
                    (cid, item.get("summaryOverride") or item.get("summary") or cid,
                     item.get("backgroundColor") or "", int(bool(item.get("primary"))),
                     item.get("accessRole", "reader"), item.get("timeZone"), shown,
                     old["sync_token"] if old else None, old["full_sync_at"] if old else None))
            gone = [cid for cid in known if cid not in keep]
            for cid in gone:
                conn.execute("DELETE FROM gcal_events WHERE calendar_id = ?", (cid,))
                conn.execute("DELETE FROM gcal_calendars WHERE id = ?", (cid,))

    def calendars(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM gcal_calendars ORDER BY is_primary DESC, title")
        return [dict(row) for row in rows]

    def set_shown(self, calendar_id: str, shown: bool) -> None:
        self.db.execute("UPDATE gcal_calendars SET shown = ? WHERE id = ?",
                        (int(shown), calendar_id))

    def primary(self) -> dict | None:
        row = self.db.query_one("SELECT * FROM gcal_calendars WHERE is_primary = 1")
        return dict(row) if row else None

    def find_calendar(self, name: str | None) -> dict | None:
        """By id or (case-insensitive) title; the primary calendar when ``name`` is empty."""
        if not name:
            return self.primary()
        wanted = name.strip().lower()
        for calendar in self.calendars():
            if wanted in (calendar["id"].lower(), calendar["title"].lower()):
                return calendar
        return None

    def time_zone(self) -> str | None:
        primary = self.primary()
        return primary["time_zone"] if primary else None

    # ----- sync state --------------------------------------------------------------------------
    def sync_state(self, calendar_id: str) -> tuple[str | None, datetime | None]:
        row = self.db.query_one("SELECT sync_token, full_sync_at FROM gcal_calendars WHERE id = ?",
                                (calendar_id,))
        if row is None:
            return None, None
        full = datetime.fromisoformat(row["full_sync_at"]) if row["full_sync_at"] else None
        return row["sync_token"], full

    def set_sync_token(self, calendar_id: str, token: str | None,
                       full_sync_at: datetime | None = None) -> None:
        if full_sync_at is None:
            self.db.execute("UPDATE gcal_calendars SET sync_token = ? WHERE id = ?",
                            (token, calendar_id))
        else:
            self.db.execute(
                "UPDATE gcal_calendars SET sync_token = ?, full_sync_at = ? WHERE id = ?",
                (token, full_sync_at.isoformat(), calendar_id))

    def reset_calendar(self, calendar_id: str) -> None:
        """Token no longer valid (410 GONE): wipe its events and forget the token."""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM gcal_events WHERE calendar_id = ?", (calendar_id,))
            conn.execute("UPDATE gcal_calendars SET sync_token = NULL WHERE id = ?",
                         (calendar_id,))

    # ----- events ------------------------------------------------------------------------------
    def apply_events(self, calendar_id: str, items: list[dict]) -> tuple[int, int]:
        """Merge one page of events: cancelled ones are removed, the rest inserted or updated.
        Returns (changed, removed)."""
        changed = removed = 0
        with self.db.transaction() as conn:
            for item in items:
                if item.get("status") == "cancelled":
                    removed += conn.execute(
                        "DELETE FROM gcal_events WHERE calendar_id = ? AND id = ?",
                        (calendar_id, item["id"])).rowcount
                    continue
                try:
                    event = event_from_item(calendar_id, item)
                except (KeyError, ValueError):
                    continue  # malformed: skip rather than lose the whole page
                conn.execute(
                    """INSERT OR REPLACE INTO gcal_events(calendar_id, id, title, all_day,
                           start_utc, end_utc, start_date, end_date, link, location)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (calendar_id, event.id, event.title, int(event.all_day),
                     event.start.isoformat() if event.start else None,
                     event.end.isoformat() if event.end else None,
                     event.start_date.isoformat() if event.start_date else None,
                     event.end_date.isoformat() if event.end_date else None,
                     event.link, event.location))
                changed += 1
        return changed, removed

    def events_between(self, start: datetime, end: datetime, shown_only: bool = True,
                       ) -> list[Event]:
        """Events overlapping [start, end) (aware datetimes), with their calendar's colour."""
        start_utc, end_utc = start.astimezone(UTC).isoformat(), end.astimezone(UTC).isoformat()
        first_day, last_day = start.date().isoformat(), end.date().isoformat()
        rows = self.db.query(
            f"""SELECT e.*, c.color FROM gcal_events e
                JOIN gcal_calendars c ON c.id = e.calendar_id
                WHERE {'c.shown = 1 AND' if shown_only else ''}
                ((e.all_day = 0 AND e.start_utc < ? AND e.end_utc > ?)
                 OR (e.all_day = 1 AND e.start_date <= ? AND e.end_date > ?))""",
            (end_utc, start_utc, last_day, first_day))
        return [self._event(row) for row in rows]

    @staticmethod
    def _event(row) -> Event:
        def moment(value):
            return datetime.fromisoformat(value) if value else None

        def day(value):
            return date.fromisoformat(value) if value else None

        return Event(row["calendar_id"], row["id"], row["title"], bool(row["all_day"]),
                     moment(row["start_utc"]), moment(row["end_utc"]), day(row["start_date"]),
                     day(row["end_date"]), row["link"] or "", row["location"] or "",
                     row["color"])

    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM gcal_events")
        return int(row["n"])

    # ----- bookkeeping -------------------------------------------------------------------------
    def last_synced(self) -> datetime | None:
        row = self.db.query_one("SELECT value FROM meta WHERE key = 'gcal_last_synced'")
        return datetime.fromisoformat(row["value"]) if row else None

    def set_last_synced(self, when: datetime) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('gcal_last_synced', ?)",
                        (when.isoformat(),))

    def clear(self) -> None:
        """Disconnect: forget every calendar and event."""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM gcal_events")
            conn.execute("DELETE FROM gcal_calendars")
            conn.execute("DELETE FROM meta WHERE key = 'gcal_last_synced'")
