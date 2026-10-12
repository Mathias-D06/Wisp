"""Locations of Wisp's data on disk (%APPDATA%\\Wisp by default)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Wisp"


def data_dir() -> Path:
    """Return the per-user data folder, creating it if needed.

    ``WISP_DATA_DIR`` overrides the location (used by tests and portable runs).
    """
    override = os.environ.get("WISP_DATA_DIR")
    if override:
        base = Path(override)
    else:
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        base = Path(appdata) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def settings_file() -> Path:
    return data_dir() / "settings.json"


def secrets_file() -> Path:
    return data_dir() / "secrets.bin"


def database_file() -> Path:
    return data_dir() / "wisp.sqlite3"


def jobs_database_file() -> Path:
    return data_dir() / "jobs.sqlite3"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_frozen() -> bool:
    """True when running from the PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def launch_command() -> str:
    """Command line that starts Wisp, quoted for the Run registry key."""
    if is_frozen():
        return f'"{sys.executable}" --background'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreter}" -m wisp --background'
