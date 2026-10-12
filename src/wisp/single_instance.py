"""One Wisp per Windows session, using a named mutex.

Source: https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw
(an existing named mutex returns a handle and GetLastError() == ERROR_ALREADY_EXISTS).
The installer's AppMutex uses the same name so setup can tell when Wisp is running.
"""

from __future__ import annotations

MUTEX_NAME = "WispAssistantMutex"


class SingleInstance:
    def __init__(self, name: str = MUTEX_NAME):
        import win32api
        import win32event
        import winerror

        self._handle = win32event.CreateMutex(None, False, name)
        self.already_running = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS

    def release(self) -> None:
        import win32api

        if self._handle:
            win32api.CloseHandle(self._handle)
            self._handle = None
