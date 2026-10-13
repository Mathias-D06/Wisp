"""Is a full-screen app or game in front on the island's monitor? (D-045)

Two documented signals:
* SHQueryUserNotificationState (shellapi.h): QUNS_RUNNING_D3D_FULL_SCREEN (an exclusive-mode
  Direct3D app) and QUNS_PRESENTATION_MODE (presentation settings) mean "don't show pop-ups".
  QUNS_BUSY ("a full-screen application is running or Presentation Settings are applied") does not
  say which monitor, so it only counts together with the check below.
* The foreground window covers the island's whole monitor (DWM extended frame bounds against
  MONITORINFO.rcMonitor, both physical pixels), is not maximized (IsZoomed: a maximized window
  can cover the monitor when the taskbar auto-hides) and isn't the desktop, the taskbar or Wisp.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from wisp.winapi import windows

QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE = 2, 3, 4
MONITOR_DEFAULTTONEAREST = 2
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
SLACK = 2  # px


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HMONITOR
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.IsZoomed.argtypes = [wintypes.HWND]


def covers(bounds: tuple[int, int, int, int] | None, monitor: tuple[int, int, int, int]) -> bool:
    if bounds is None:
        return False
    return (bounds[0] <= monitor[0] + SLACK and bounds[1] <= monitor[1] + SLACK
            and bounds[2] >= monitor[2] - SLACK and bounds[3] >= monitor[3] - SLACK)


def decide(state: int | None, same_monitor: bool, bounds, monitor, zoomed: bool,
           shell_or_ours: bool) -> bool:
    """Pure decision: hide the island on ``monitor``?"""
    if state in (QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE):
        return True
    if not same_monitor or shell_or_ours or zoomed:
        return False
    return covers(bounds, monitor)


def notification_state() -> int | None:
    value = ctypes.c_int(0)
    try:
        result = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(value))
    except OSError:
        return None
    return value.value if result == 0 else None


def monitor_rect(hwnd: int) -> tuple[int, tuple[int, int, int, int]] | None:
    handle = _user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not handle or not _user32.GetMonitorInfoW(handle, ctypes.byref(info)):
        return None
    r = info.rcMonitor
    return int(handle), (r.left, r.top, r.right, r.bottom)


def fullscreen_over(island_hwnd: int) -> bool:
    """True when the island should hide because a full-screen app is in front of it."""
    island = monitor_rect(island_hwnd)
    foreground = _user32.GetForegroundWindow()
    if island is None or not foreground:
        return decide(notification_state(), False, None, (0, 0, 0, 0), False, True)
    fg_monitor = monitor_rect(foreground)
    ours = windows.pid_of(foreground) == os.getpid()
    shell = windows.class_name(foreground) in SHELL_CLASSES
    return decide(notification_state(), fg_monitor is not None and fg_monitor[0] == island[0],
                  windows.frame_bounds(foreground), island[1], bool(_user32.IsZoomed(foreground)),
                  shell or ours)
