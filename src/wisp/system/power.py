"""Lock, sleep, restart, shut down.

Sources: LockWorkStation (user32); SetSuspendState(bHibernate=FALSE, …) needs SE_SHUTDOWN_NAME
enabled via AdjustTokenPrivileges (powrprof docs); restart/shut down use the documented
`shutdown /r` and `shutdown /s` commands (learn.microsoft.com windows-commands/shutdown). Every
caller confirms first (UI dialog or confirm-tier tool).
"""

from __future__ import annotations

import ctypes
import subprocess

CREATE_NO_WINDOW = 0x08000000


def lock() -> None:
    if not ctypes.windll.user32.LockWorkStation():
        raise OSError("Windows refused to lock.")


def _enable_shutdown_privilege() -> None:
    import win32api
    import win32security

    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),
        win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY)
    luid = win32security.LookupPrivilegeValue(None, win32security.SE_SHUTDOWN_NAME)
    win32security.AdjustTokenPrivileges(token, False,
                                        [(luid, win32security.SE_PRIVILEGE_ENABLED)])


def sleep() -> None:
    _enable_shutdown_privilege()
    if not ctypes.windll.powrprof.SetSuspendState(False, False, False):
        raise OSError("Windows refused to sleep.")


def restart() -> None:
    subprocess.run(["shutdown", "/r", "/t", "0"], check=True, creationflags=CREATE_NO_WINDOW)


def shutdown() -> None:
    subprocess.run(["shutdown", "/s", "/t", "0"], check=True, creationflags=CREATE_NO_WINDOW)
