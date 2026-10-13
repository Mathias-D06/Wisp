"""Top-level window enumeration and control.

Sources (learn.microsoft.com): EnumWindows, GetWindowTextW, IsWindowVisible, IsIconic,
ShowWindow (SW_MINIMIZE=6, SW_MAXIMIZE=3, SW_RESTORE=9), PostMessageW + WM_CLOSE (lets the app
ask to save), SetForegroundWindow (restrictions), DwmGetWindowAttribute (DWMWA_CLOAKED=14,
DWMWA_EXTENDED_FRAME_BOUNDS=9), QueryFullProcessImageNameW, OpenProcessToken/TokenElevation.
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes
from dataclasses import dataclass

log = logging.getLogger(__name__)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi")
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsZoomed.argtypes = [wintypes.HWND]
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = wintypes.LONG
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_user32.OpenInputDesktop.restype = wintypes.HANDLE
_user32.CloseDesktop.argtypes = [wintypes.HANDLE]
_user32.WindowFromPoint.argtypes = [wintypes.POINT]
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                 wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
_dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                                          wintypes.DWORD]
_advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                       ctypes.POINTER(wintypes.HANDLE)]
_advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                          wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

GW_OWNER = 4
GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
WM_CLOSE = 0x0010
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION_CLASS = 20  # TokenElevation
DESKTOP_SWITCHDESKTOP = 0x0100


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    process: str
    pid: int
    minimized: bool
    foreground: bool

    def as_dict(self) -> dict:
        return {"title": self.title, "app": self.process, "minimized": self.minimized,
                "active": self.foreground}


def _title(hwnd: int) -> str:
    length = _user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _cloaked(hwnd: int) -> bool:
    value = wintypes.DWORD()
    result = _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value),
                                           ctypes.sizeof(value))
    return result == 0 and value.value != 0


def pid_of(hwnd: int) -> int:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def process_path(pid: int) -> str:
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        _kernel32.CloseHandle(handle)


def is_process_elevated(pid: int) -> bool:
    """True if the process runs elevated, or if Windows will not let us look (treated as
    elevated/protected so callers explain the limit instead of failing silently)."""
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return True
    token = wintypes.HANDLE()
    try:
        if not _advapi32.OpenProcessToken(handle, TOKEN_QUERY, ctypes.byref(token)):
            return True
        elevation = wintypes.DWORD()
        returned = wintypes.DWORD()
        ok = _advapi32.GetTokenInformation(token, TOKEN_ELEVATION_CLASS, ctypes.byref(elevation),
                                           ctypes.sizeof(elevation), ctypes.byref(returned))
        return bool(ok and elevation.value)
    finally:
        if token:
            _kernel32.CloseHandle(token)
        _kernel32.CloseHandle(handle)


def self_elevated() -> bool:
    return is_process_elevated(os.getpid())


def input_desktop_available() -> bool:
    """False while the secure desktop (UAC prompt, Ctrl+Alt+Del) or lock screen is active."""
    desktop = _user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not desktop:
        return False
    _user32.CloseDesktop(desktop)
    return True


def _is_alt_tab_window(hwnd: int) -> bool:
    if not _user32.IsWindowVisible(hwnd) or _cloaked(hwnd):
        return False
    if not _user32.GetWindowTextLengthW(hwnd):
        return False
    ex_style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex_style & WS_EX_TOOLWINDOW:
        return False
    owner = _user32.GetWindow(hwnd, GW_OWNER)
    return not owner or bool(ex_style & WS_EX_APPWINDOW)


def list_windows() -> list[WindowInfo]:
    handles: list[int] = []

    def collect(hwnd: int, _lparam: int) -> bool:
        if _is_alt_tab_window(hwnd):
            handles.append(hwnd)
        return True

    _user32.EnumWindows(WNDENUMPROC(collect), 0)
    foreground = _user32.GetForegroundWindow()
    own_pid = os.getpid()
    result = []
    for hwnd in handles:
        pid = pid_of(hwnd)
        if pid == own_pid:
            continue
        path = process_path(pid)
        name = os.path.splitext(os.path.basename(path))[0] if path else "unknown"
        result.append(WindowInfo(hwnd, _title(hwnd), name, pid, bool(_user32.IsIconic(hwnd)),
                                 hwnd == foreground))
    return result


def window_at(x: int, y: int) -> WindowInfo | None:
    """Top-level window under a physical-pixel point (WindowFromPoint + GetAncestor GA_ROOT)."""
    hwnd = _user32.WindowFromPoint(wintypes.POINT(x, y))
    if not hwnd:
        return None
    root = _user32.GetAncestor(hwnd, GA_ROOT) or hwnd
    pid = pid_of(root)
    path = process_path(pid)
    name = os.path.splitext(os.path.basename(path))[0] if path else "unknown"
    return WindowInfo(root, _title(root), name, pid, bool(_user32.IsIconic(root)),
                      root == _user32.GetForegroundWindow())


def foreground_window() -> WindowInfo | None:
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = pid_of(hwnd)
    path = process_path(pid)
    name = os.path.splitext(os.path.basename(path))[0] if path else "unknown"
    return WindowInfo(hwnd, _title(hwnd), name, pid, bool(_user32.IsIconic(hwnd)), True)


def is_window(hwnd: int) -> bool:
    return bool(_user32.IsWindow(hwnd))


def activate(hwnd: int) -> bool:
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, SW_RESTORE)
    if _user32.SetForegroundWindow(hwnd) and _user32.GetForegroundWindow() == hwnd:
        return True
    # UNDOCUMENTED (DECISIONS.md D-016): attaching to the foreground thread's input usually
    # lets SetForegroundWindow succeed. If not, Windows flashes the taskbar button instead.
    current = _kernel32.GetCurrentThreadId()
    target = _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(), None)
    attached = bool(target) and target != current and _user32.AttachThreadInput(current, target,
                                                                                True)
    try:
        _user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            _user32.AttachThreadInput(current, target, False)
    return _user32.GetForegroundWindow() == hwnd


def minimize(hwnd: int) -> None:
    _user32.ShowWindow(hwnd, SW_MINIMIZE)


def maximize(hwnd: int) -> None:
    _user32.ShowWindow(hwnd, SW_MAXIMIZE)


def restore(hwnd: int) -> None:
    _user32.ShowWindow(hwnd, SW_RESTORE)


def request_close(hwnd: int) -> bool:
    """Politely ask the window to close (WM_CLOSE), as clicking X does."""
    return bool(_user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


def frame_bounds(hwnd: int) -> tuple[int, int, int, int] | None:
    """Visible window rectangle (left, top, right, bottom) in physical screen pixels."""
    rect = wintypes.RECT()
    result = _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                           ctypes.byref(rect), ctypes.sizeof(rect))
    if result != 0:
        return None
    return rect.left, rect.top, rect.right, rect.bottom


# ----- the island's window behaviour (D-045) -----------------------------------------------------
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


def ex_style(hwnd: int) -> int:
    return int(_user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE))


def set_no_activate(hwnd: int) -> None:
    """WS_EX_NOACTIVATE: clicking the window doesn't make it the foreground window (Extended
    Window Styles, learn.microsoft.com); SetForegroundWindow still can, when allowed."""
    style = ex_style(hwnd)
    if not style & WS_EX_NOACTIVATE:
        _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)


def set_foreground(hwnd: int) -> bool:
    """Plain SetForegroundWindow (allowed after the user clicked our window: "the calling
    process received the last input event"); no fallbacks."""
    return bool(hwnd) and bool(_user32.SetForegroundWindow(hwnd))


def foreground_hwnd() -> int:
    return int(_user32.GetForegroundWindow() or 0)


def place_below(hwnd: int, above: int) -> None:
    """Put ``hwnd`` directly behind ``above`` in the Z order without activating it."""
    _user32.SetWindowPos(hwnd, above, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def button_down(vk: int) -> bool:
    """GetAsyncKeyState: the most significant bit is set while the key or button is down."""
    return _user32.GetAsyncKeyState(vk) < 0
