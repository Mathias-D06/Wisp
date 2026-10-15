"""The services container passed to tool handlers (``ctx.services``) and UI pages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from wisp.db import Database
from wisp.keystore import KeyStore
from wisp.settings import SettingsStore


@dataclass
class Services:
    settings: SettingsStore
    keystore: KeyStore
    db: Database
    ui: Any
    notify: Callable[[str, str], None]
    action_log: Any = None
    stats: Any = None
    confirmations: Any = None
    taint: Any = None
    registry: Any = None
    dispatcher: Any = None
    live: Any = None
    voice: Any = None
    mic: Any = None
    player: Any = None
    app_index: Any = None
    todos: Any = None
    tasks: Any = None
    memory: Any = None
    scheduler: Any = None
    clipboard: Any = None
    media: Any = None
    calendar: Any = None  # CalendarService (D-050)
    shelf: Any = None  # files.shelf.Shelf (D-051)
    finder: Any = None  # files.finder.FileFinder
    phone: Any = None  # phone.service.PhoneLink
    share_files: Any = None  # callable(list[Path]): the Windows share sheet
    open_files_tab: Any = None  # callable(): show the island's Files & Share tab
    assist: Any = None  # assist.service.ScreenAssist (D-052)
    watcher: Any = None  # assist.service.Watcher
    blocklist: Any = None  # callable() -> assist.privacy.Blocklist
    usage: Any = None  # stores.usage.UsageStore
    system: Any = None
    overlay: Any = None
    last_capture: Any = None
    """(screen.Capture, monotonic time) of the latest look_at_screen, for raw clicks."""
