"""Spike: confirm the bundled SQLite has FTS5 with bm25() ranking (used by the memory store).

Run: .venv\\Scripts\\python spikes\\sqlite_fts5.py
"""

import sqlite3

print("sqlite", sqlite3.sqlite_version)
conn = sqlite3.connect(":memory:")
conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
conn.executemany(
    "INSERT INTO t VALUES (?)",
    [("my sister's birthday is in May",), ("I prefer dark mode",), ("work starts at 9",)],
)
rows = conn.execute("SELECT x, bm25(t) FROM t WHERE t MATCH ? ORDER BY bm25(t)", ("birthday",))
print(rows.fetchall())
