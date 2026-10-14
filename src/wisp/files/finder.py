"""Finding files (D-051): search, recent files and Downloads.

Search asks the Windows Search index first: its OLE DB provider (Search.CollatorDSO) through ADO,
with Windows Search SQL over SystemIndex. That is Microsoft's documented way to query the index
from an app, and answers in tens of milliseconds where walking the folders takes seconds. The
query is restricted to the user's own folders (SCOPE='file:…') and matches the file name with
LIKE (wildcards in the person's text are escaped with brackets, quotes doubled). Results are
ranked with rapidfuzz, so word order and small typos still find the file; a second, looser query
(the first three letters of each word) feeds the fuzzy ranking when the exact one finds little.
If the index isn't available (the Windows Search service is off), the folders are walked
instead (wisp.winapi.files.search_files).
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

from wisp.winapi import files as fs

log = logging.getLogger(__name__)

CONNECTION = "Provider=Search.CollatorDSO;Extended Properties='Application=Windows';"
INDEX_TOP = 200
MIN_SCORE = 60
PARTIAL_DOWNLOADS = {".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload"}
HIDDEN_NAMES = {"desktop.ini", "thumbs.db"}


@dataclass(frozen=True)
class FileResult:
    path: Path
    modified: float
    score: float = 0.0

    @property
    def name(self) -> str:
        return self.path.name

    def as_dict(self) -> dict:
        return {"name": self.path.name, "path": str(self.path),
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.modified))}


# ----- Windows Search SQL ---------------------------------------------------------------------
def string_literal(text: str) -> str:
    """Inside '…': a single quote is written twice (Windows Search SQL literals)."""
    return text.replace("'", "''")


def like_literal(text: str) -> str:
    """A LIKE pattern that matches ``text`` literally: %, _ and [ go inside brackets."""
    escaped = "".join(f"[{ch}]" if ch in "%_[" else ch for ch in text)
    return string_literal(escaped)


def index_sql(terms: list[str], scopes: list[Path], top: int = INDEX_TOP) -> str:
    names = " AND ".join(f"System.FileName LIKE '%{like_literal(term)}%'" for term in terms)
    where = " OR ".join(f"SCOPE='file:{string_literal(scope.as_posix())}'" for scope in scopes)
    return (f"SELECT TOP {int(top)} System.ItemPathDisplay, System.DateModified "
            f"FROM SystemIndex WHERE ({where}) AND {names} ORDER BY System.DateModified DESC")


def query_index(sql: str) -> list[tuple[Path, float]]:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()  # this (worker) thread may not have COM yet
    connection = win32com.client.Dispatch("ADODB.Connection")
    connection.Open(CONNECTION)
    try:
        records = win32com.client.Dispatch("ADODB.Recordset")
        records.Open(sql, connection)
        rows = []
        while not records.EOF:
            path = records.Fields.Item("System.ItemPathDisplay").Value
            modified = records.Fields.Item("System.DateModified").Value
            if path:
                rows.append((Path(path), modified.timestamp() if modified else 0.0))
            records.MoveNext()
        records.Close()
        return rows
    finally:
        connection.Close()


# ----- ranking ------------------------------------------------------------------------------------
def score(query: str, name: str, modified: float, now: float | None = None) -> float:
    """How well ``name`` matches: fuzzy (word order and small typos forgiven), plus up to 8
    points for files changed recently."""
    stem = Path(name).stem.lower()
    needle = query.lower().strip()
    match = max(fuzz.WRatio(needle, stem), fuzz.WRatio(needle, name.lower()))
    if needle and needle in name.lower():
        match = max(match, 90)
    age_days = max(0.0, ((now or time.time()) - modified) / 86400)
    return match + 8 * math.exp(-age_days / 30)


def rank(query: str, candidates: list[tuple[Path, float]], limit: int,
         now: float | None = None) -> list[FileResult]:
    seen: dict[str, FileResult] = {}
    for path, modified in candidates:
        key = str(path).lower()
        if key in seen or path.name.lower() in HIDDEN_NAMES:
            continue
        value = score(query, path.name, modified, now)
        if value >= MIN_SCORE:
            seen[key] = FileResult(path, modified, value)
    return sorted(seen.values(), key=lambda r: (r.score, r.modified), reverse=True)[:limit]


class FileFinder:
    def __init__(self, roots: list[Path] | None = None, index=query_index,
                 downloads_folder: Path | None = None) -> None:
        self._roots = roots
        self._index = index
        self._downloads = downloads_folder
        self.used_index = True

    def roots(self) -> list[Path]:
        return self._roots or [Path.home()]

    def search(self, query: str, limit: int = 20) -> list[FileResult]:
        terms = [t for t in query.split() if t]
        if not terms or len(query.strip()) < 2:
            return []
        try:
            rows = self._index(index_sql(terms, self.roots()))
            if len(rows) < limit:
                loose = [t[:3] for t in terms]
                if loose != terms:
                    rows += self._index(index_sql(loose, self.roots()))
            self.used_index = True
        except Exception as exc:  # the Windows Search service is off or the provider missing
            log.info("Windows Search index unavailable (%s); walking folders",
                     type(exc).__name__)
            self.used_index = False
            hits = fs.search_files(query, None if self._roots is None else self._roots,
                                   limit=limit * 2, time_budget_s=2.5)
            rows = [(hit.path, hit.modified) for hit in hits]
        return rank(query, rows, limit)

    def downloads_folder(self) -> Path:
        if self._downloads is not None:
            return self._downloads
        try:
            from win32com.shell import shell, shellcon

            return Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Downloads))
        except Exception:
            return Path.home() / "Downloads"

    def downloads(self, limit: int = 12) -> list[FileResult]:
        """Newest finished downloads first (partial downloads and desktop.ini skipped)."""
        folder = self.downloads_folder()
        entries = []
        try:
            with os.scandir(folder) as scan:
                for entry in scan:
                    name = entry.name
                    if (name.lower() in HIDDEN_NAMES or name.startswith(".")
                            or Path(name).suffix.lower() in PARTIAL_DOWNLOADS):
                        continue
                    try:
                        entries.append(FileResult(Path(entry.path), entry.stat().st_mtime))
                    except OSError:
                        continue
        except OSError:
            return []
        entries.sort(key=lambda r: r.modified, reverse=True)
        return entries[:limit]

    def latest_download(self) -> FileResult | None:
        files = [r for r in self.downloads(20) if r.path.is_file()]
        return files[0] if files else None

    @staticmethod
    def recent(limit: int = 12) -> list[FileResult]:
        return [FileResult(hit.path, hit.modified) for hit in fs.recent_files(None, limit)]
