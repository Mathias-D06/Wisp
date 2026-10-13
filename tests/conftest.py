from __future__ import annotations

import sys

import pytest

if sys.platform == "win32":
    # Same as the app: comtypes must first be imported on the main thread (see winapi/uia.py).
    import comtypes.client  # noqa: F401


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Every test gets its own %APPDATA%\\Wisp so real user data is never touched."""
    data = tmp_path / "wispdata"
    monkeypatch.setenv("WISP_DATA_DIR", str(data))
    return data


@pytest.fixture
def db(tmp_path):
    from wisp.db import Database

    database = Database(tmp_path / "test.sqlite3")
    yield database
    database.close()


def pytest_collection_modifyitems(config, items):
    if sys.platform == "win32":
        return
    skip = pytest.mark.skip(reason="Windows-only test")
    for item in items:
        if "windows" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def no_motion():
    """UI tests see end states at once; animation tests opt in with ``motion.force(True)``."""
    from wisp.ui import motion

    motion.force(False)
    yield
    motion.force(None)
