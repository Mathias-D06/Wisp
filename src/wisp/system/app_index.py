"""Index of launchable apps: every Start-menu app (desktop and Store) plus Start Menu shortcuts.

Source: https://learn.microsoft.com/en-us/windows/configuration/store/find-aumid — the Apps
folder ``shell:::{4234d49b-0245-4df3-b780-3893943456e1}`` lists installed apps; each item's
``Path`` is its AppUserModelID (proven by ``spikes/apps_folder.py``: 195 apps, ParseName round
trip). Launching uses the item's default verb (FolderItem.InvokeVerb), never "Run as admin".
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

from wisp.db import Database

log = logging.getLogger(__name__)

APPS_FOLDER = "shell:::{4234d49b-0245-4df3-b780-3893943456e1}"
DOC_SUFFIXES = {".chm", ".htm", ".html", ".url", ".txt", ".pdf", ".rtf", ".md"}
SKIP_WORDS = ("uninstall", "readme", "documentation", "release notes", "license", "help")


@dataclass
class AppEntry:
    id: int
    name: str
    target: str
    kind: str  # "aumid" or "path"
    launch_count: int = 0
    pinned: bool = False


def _keep(name: str, target: str) -> bool:
    lowered = name.lower()
    if any(word in lowered for word in SKIP_WORDS):
        return False
    return Path(target).suffix.lower() not in DOC_SUFFIXES


def score(query: str, name: str, launch_count: int = 0) -> float:
    q, n = query.lower().strip(), name.lower()
    if not q:
        return 0.0
    if q == n:
        return 120.0
    value = max(fuzz.WRatio(q, n), fuzz.token_set_ratio(q, n))
    if n.startswith(q):
        value += 8
    return value + min(launch_count, 10) * 0.5


class AppIndex:
    def __init__(self, db: Database):
        self._db = db
        self._lock = threading.Lock()
        self.last_error: str | None = None

    # ----- building --------------------------------------------------------------------------
    @staticmethod
    def _apps_folder() -> list[tuple[str, str, str]]:
        import win32com.client

        shell = win32com.client.Dispatch("Shell.Application")
        folder = shell.NameSpace(APPS_FOLDER)
        result = []
        for item in folder.Items():
            name, target = str(item.Name), str(item.Path)
            if not name or not target or not _keep(name, target):
                continue
            is_file = len(target) > 2 and target[1] == ":" and os.path.exists(target)
            result.append((name, target, "path" if is_file else "aumid"))
        return result

    @staticmethod
    def _start_menu_shortcuts() -> list[tuple[str, str, str]]:
        roots = [
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows"
            / "Start Menu" / "Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs",
        ]
        result = []
        for root in roots:
            if not root.is_dir():
                continue
            for link in root.rglob("*.lnk"):
                if _keep(link.stem, str(link)):
                    result.append((link.stem, str(link), "path"))
        return result

    def refresh(self) -> int:
        """Rebuild from Windows; keeps launch counts and pins. Needs COM on this thread."""
        try:
            found = self._apps_folder()
        except Exception as exc:
            self.last_error = f"Apps folder unavailable: {exc}"
            log.warning(self.last_error)
            found = []
        names = {name.lower() for name, _, _ in found}
        found += [s for s in self._start_menu_shortcuts() if s[0].lower() not in names]
        with self._lock, self._db.transaction() as conn:
            existing = {(r["name"], r["target"]) for r in conn.execute(
                "SELECT name, target FROM app_index")}
            current = {(name, target) for name, target, _ in found}
            for name, target in existing - current:
                conn.execute("DELETE FROM app_index WHERE name=? AND target=?", (name, target))
            for name, target, kind in found:
                conn.execute(
                    "INSERT OR IGNORE INTO app_index(name, target, kind) VALUES (?, ?, ?)",
                    (name, target, kind),
                )
        log.info("App index refreshed: %d apps", len(found))
        return len(found)

    def refresh_in_background(self) -> threading.Thread:
        def work() -> None:
            import pythoncom

            pythoncom.CoInitialize()
            try:
                self.refresh()
            finally:
                pythoncom.CoUninitialize()

        thread = threading.Thread(target=work, name="app-index", daemon=True)
        thread.start()
        return thread

    # ----- queries ---------------------------------------------------------------------------
    def _row(self, row) -> AppEntry:
        return AppEntry(row["id"], row["name"], row["target"], row["kind"], row["launch_count"],
                        bool(row["pinned"]))

    def all(self) -> list[AppEntry]:
        rows = self._db.query(
            "SELECT * FROM app_index ORDER BY pinned DESC, launch_count DESC, name COLLATE NOCASE")
        return [self._row(r) for r in rows]

    def count(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS n FROM app_index")
        return int(row["n"]) if row else 0

    def search(self, query: str, limit: int = 5) -> list[tuple[AppEntry, float]]:
        ranked = sorted(((entry, score(query, entry.name, entry.launch_count))
                         for entry in self.all()), key=lambda pair: pair[1], reverse=True)
        return ranked[:limit]

    def set_pinned(self, entry_id: int, pinned: bool) -> None:
        self._db.execute("UPDATE app_index SET pinned=? WHERE id=?", (int(pinned), entry_id))

    # ----- launching -------------------------------------------------------------------------
    def launch(self, entry: AppEntry) -> None:
        if entry.kind == "aumid":
            import win32com.client

            shell = win32com.client.Dispatch("Shell.Application")
            item = shell.NameSpace(APPS_FOLDER).ParseName(entry.target)
            if item is not None:
                item.InvokeVerb()  # default verb ("Open"); never "Run as administrator"
            else:
                os.startfile(f"shell:AppsFolder\\{entry.target}")
        else:
            os.startfile(entry.target)
        self._db.execute("UPDATE app_index SET launch_count = launch_count + 1 WHERE id=?",
                         (entry.id,))
        log.info("Launched %s", entry.name)
