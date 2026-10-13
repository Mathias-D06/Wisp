"""Windows 11 window chrome through documented DWM attributes (DwmSetWindowAttribute,
learn.microsoft.com dwmapi DWMWINDOWATTRIBUTE / DWM_SYSTEMBACKDROP_TYPE; D-042):

* ``DWMWA_USE_IMMERSIVE_DARK_MODE`` (20, BOOL, Windows 11 build 22000+): dark title bar.
* ``DWMWA_WINDOW_CORNER_PREFERENCE`` (33, build 22000+): ``DWMWCP_ROUND`` (2) corners.
* ``DWMWA_SYSTEMBACKDROP_TYPE`` (38, build 22621+): ``DWMSBT_MAINWINDOW`` (2) = Mica.

On older builds nothing is set and the window keeps its solid theme colours (Windows 10
fallback). Every call is best-effort: a failure never stops a window from showing.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWCP_ROUND = 2
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2
BUILD_ROUNDED = 22000
BUILD_BACKDROP = 22621


def windows_build() -> int:
    try:
        return sys.getwindowsversion().build
    except AttributeError:  # not Windows
        return 0


def _set(hwnd: int, attribute: int, value: int) -> bool:
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        data = ctypes.c_int(value)
        result = dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), ctypes.c_uint(attribute),
                                              ctypes.byref(data), ctypes.sizeof(data))
    except OSError as exc:
        log.debug("DwmSetWindowAttribute(%d) unavailable: %s", attribute, exc)
        return False
    if result != 0:
        log.debug("DwmSetWindowAttribute(%d) failed: 0x%08x", attribute, result & 0xFFFFFFFF)
    return result == 0


def style_window(hwnd: int, dark: bool, backdrop: bool = True) -> dict[str, bool]:
    """Apply dark title bar, rounded corners and Mica where the build supports them."""
    build = windows_build()
    applied = {"dark_title": False, "rounded": False, "mica": False}
    if build >= BUILD_ROUNDED:
        applied["dark_title"] = _set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark))
        applied["rounded"] = _set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
    if build >= BUILD_BACKDROP:
        applied["mica"] = _set(hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                               DWMSBT_MAINWINDOW if backdrop else DWMSBT_NONE)
    return applied


class MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]


def extend_frame(hwnd: int) -> bool:
    """DwmExtendFrameIntoClientArea with -1 margins ("sheet of glass"), so the backdrop shows
    through the transparent parts of the client area."""
    try:
        margins = MARGINS(-1, -1, -1, -1)
        result = ctypes.WinDLL("dwmapi").DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd),
                                                                     ctypes.byref(margins))
    except OSError:
        return False
    return result == 0


def mica_supported() -> bool:
    return windows_build() >= BUILD_BACKDROP
