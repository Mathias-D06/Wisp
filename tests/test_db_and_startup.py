from __future__ import annotations

import pytest

from wisp import startup
from wisp.db import SCHEMA_VERSION, Database


def test_schema_created_and_idempotent(tmp_path):
    path = tmp_path / "w.sqlite3"
    Database(path).close()
    database = Database(path)  # second open re-runs migrations safely
    tables = {r["name"] for r in database.query("SELECT name FROM sqlite_master")}
    for table in ("todos", "memories", "memories_fts", "clipboard_items", "action_log",
                  "stats_events", "app_index", "tasks"):
        assert table in tables
    version = database.query_one("SELECT value FROM meta WHERE key='schema_version'")
    assert version["value"] == str(SCHEMA_VERSION)
    database.close()


@pytest.mark.windows
def test_run_key_toggle(monkeypatch):
    monkeypatch.setattr(startup, "VALUE_NAME", "WispPytestProbe")
    try:
        startup.set_enabled(True, command='"C:\\nowhere\\wisp.exe" --background')
        assert startup.is_enabled()
        startup.set_enabled(False)
        assert not startup.is_enabled()
        startup.set_enabled(False)  # idempotent
    finally:
        startup.set_enabled(False)


@pytest.mark.windows
def test_run_key_rejects_long_command(monkeypatch):
    monkeypatch.setattr(startup, "VALUE_NAME", "WispPytestProbe")
    with pytest.raises(ValueError):
        startup.set_enabled(True, command="x" * 300)
