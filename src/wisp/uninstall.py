"""Uninstalling Wisp from inside Wisp (D-061).

The installer (Inno Setup) puts its uninstaller, ``unins000.exe``, next to ``Wisp.exe``. It is
also reachable from Settings → Apps and from the Start menu's "Uninstall Wisp".

The uninstaller checks Wisp's mutex at start-up (AppMutex) and refuses while Wisp runs, so the
app can't simply start it and quit. Instead it starts a second ``Wisp.exe --run-uninstaller
<pid>``. That copy waits for this process to exit (OpenProcess + WaitForSingleObject) and then
starts the uninstaller. The waiter takes no mutex, never starts the app, and exits at once
afterwards, before the uninstaller asks for confirmation and removes any files.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

UNINSTALLER = "unins000.exe"  # what Inno Setup writes for a single app in a folder
WAIT_MS = 30_000
SYNCHRONIZE = 0x00100000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def uninstaller_path(executable: str | None = None, frozen: bool | None = None) -> Path | None:
    """The installed copy's uninstaller, or None (running from source, or not installed)."""
    executable = executable or sys.executable
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not frozen:
        return None
    folder = Path(executable).parent
    preferred = folder / UNINSTALLER
    if preferred.is_file():
        return preferred
    # Inno documents only "unins*.*" in {app} (UninstallFilesDir); take the first such exe
    others = sorted(folder.glob("unins*.exe"))
    return others[0] if others else None


def start_waiter(pid: int, executable: str | None = None,
                 popen: Callable[..., object] = subprocess.Popen) -> None:
    """Start ``Wisp.exe --run-uninstaller <pid>``, detached from this process."""
    command = [executable or sys.executable, "--run-uninstaller", str(pid)]
    log.info("Starting the uninstaller once Wisp has closed")
    popen(command, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, close_fds=True)


def wait_for_exit(pid: int, timeout_ms: int = WAIT_MS) -> bool:
    """True once process ``pid`` has exited (or doesn't exist), False on timeout."""
    import pywintypes
    import win32api
    import win32event

    try:
        handle = win32api.OpenProcess(SYNCHRONIZE, False, pid)
    except pywintypes.error:
        return True  # already gone
    try:
        return win32event.WaitForSingleObject(handle, timeout_ms) == win32event.WAIT_OBJECT_0
    finally:
        win32api.CloseHandle(handle)


def run_uninstaller(pid: int, executable: str | None = None,
                    wait: Callable[[int], bool] = wait_for_exit,
                    popen: Callable[..., object] = subprocess.Popen) -> int:
    """``Wisp.exe --run-uninstaller <pid>``: wait for Wisp to close, then start its uninstaller."""
    uninstaller = uninstaller_path(executable, frozen=True)
    if uninstaller is None:
        return 2
    if not wait(pid):
        return 3  # Wisp didn't close: the uninstaller would only refuse
    popen([str(uninstaller)], creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
          close_fds=True)
    return 0
