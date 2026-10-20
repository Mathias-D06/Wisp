from __future__ import annotations

import gc
import logging
import sys
import threading

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


@pytest.fixture
def wisp_app(qtbot, isolated_data_dir, monkeypatch):
    """A whole WispApp (in the background, with this test's data folder), quit and torn down
    afterwards.

    * WispApp sets up logging and the exception hooks for the whole process: put back.
    * ``quit()`` stops the services but leaves the windows: the real app's process ends right
      after. Here the process goes on, so the windows the app made are closed and deleted now.
      Left alive, two finished apps (database closed, loop stopped) were destroyed by PySide6's
      own shutdown at exit, which crashed the test run after "all passed" (0xC0000005 /
      0xC0000409: CI's "exit code 1", D-059).
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    from wisp.app import WispApp

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    qt = QApplication.instance()
    before = set(qt.topLevelWidgets())
    wisp = WispApp(qt, background=True)
    try:
        yield wisp
    finally:
        wisp.quit()
        for widget in qt.topLevelWidgets():
            if widget not in before:
                widget.close()
                widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()
        for handler in root.handlers:
            if handler not in handlers:
                handler.close()
        root.handlers[:] = handlers
        root.setLevel(level)


@pytest.fixture(autouse=True)
def no_motion():
    """UI tests see end states at once; animation tests opt in with ``motion.force(True)``."""
    from wisp.ui import motion

    motion.force(False)
    yield
    motion.force(None)
