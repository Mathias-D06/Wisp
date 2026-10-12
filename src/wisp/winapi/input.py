"""Keyboard and mouse injection with SendInput.

Sources: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
(UIPI: input cannot reach higher-integrity windows, and failure is silent),
https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes.
Every event Wisp injects carries ``WISP_SIGNATURE`` in dwExtraInfo so Wisp's own keyboard hook
can ignore it.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

WISP_SIGNATURE = 0x57495350  # "WISP"

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
WHEEL_DELTA = 120

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU = range(0xA0, 0xA6)
VK_MASK = 0xE8  # documented as "Unassigned"
VK_V = 0x56

_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, VK_RCONTROL, VK_RMENU,
             VK_LWIN, VK_RWIN, 0x5D, 0x6F, 0x90}

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_user32.SendInput.restype = wintypes.UINT
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.GetSystemMetrics.argtypes = [ctypes.c_int]
_user32.GetSystemMetrics.restype = ctypes.c_int


def _key(vk: int, up: bool) -> INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in _EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    item = INPUT(type=INPUT_KEYBOARD)
    item.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=WISP_SIGNATURE)
    return item


def _send(items: list[INPUT]) -> int:
    if not items:
        return 0
    array = (INPUT * len(items))(*items)
    return _user32.SendInput(len(items), array, ctypes.sizeof(INPUT))


def send_keys(events: list[tuple[int, bool]]) -> int:
    """events: (virtual key, is_key_up)."""
    return _send([_key(vk, up) for vk, up in events])


def tap(vk: int) -> int:
    return send_keys([(vk, False), (vk, True)])


def send_mask_key() -> int:
    """Tap an unassigned key so the shell treats a held Win/Alt as part of a combination
    (stops the Start menu / menu bar on release). UNDOCUMENTED shell behaviour; see
    DECISIONS.md."""
    return tap(VK_MASK)


def is_down(vk: int) -> bool:
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def release_held_modifiers() -> list[int]:
    """Send key-ups for modifiers still physically/logically down so a synthetic shortcut is
    not combined with them (SendInput does not reset keyboard state)."""
    held = [vk for vk in (VK_LCONTROL, VK_RCONTROL, VK_LSHIFT, VK_RSHIFT, VK_LMENU, VK_RMENU,
                          VK_LWIN, VK_RWIN) if is_down(vk)]
    if held:
        if any(vk in (VK_LWIN, VK_RWIN, VK_LMENU, VK_RMENU) for vk in held):
            send_mask_key()
        send_keys([(vk, True) for vk in held])
    return held


def combo(modifiers: list[int], key: int) -> int:
    events = [(m, False) for m in modifiers] + [(key, False), (key, True)]
    events += [(m, True) for m in reversed(modifiers)]
    return send_keys(events)


def paste_shortcut() -> int:
    """Ctrl+V into the focused window."""
    return combo([VK_CONTROL], VK_V)


def type_text(text: str, delay_s: float = 0.0) -> int:
    """Type Unicode text with KEYEVENTF_UNICODE (layout-independent)."""
    sent = 0
    for char in text:
        units = char.encode("utf-16-le")
        for index in range(0, len(units), 2):
            code = int.from_bytes(units[index:index + 2], "little")
            down = INPUT(type=INPUT_KEYBOARD)
            down.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0,
                                 dwExtraInfo=WISP_SIGNATURE)
            up = INPUT(type=INPUT_KEYBOARD)
            up.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                               time=0, dwExtraInfo=WISP_SIGNATURE)
            sent += _send([down, up])
        if delay_s:
            time.sleep(delay_s)
    return sent


def mouse_click(x: int, y: int, button: str = "left", double: bool = False) -> int:
    """Click at virtual-screen pixel coordinates (process is per-monitor DPI aware)."""
    left = _user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    top = _user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    width = max(1, _user32.GetSystemMetrics(78) - 1)  # SM_CXVIRTUALSCREEN
    height = max(1, _user32.GetSystemMetrics(79) - 1)  # SM_CYVIRTUALSCREEN
    ax = int((x - left) * 65535 / width)
    ay = int((y - top) * 65535 / height)
    move = INPUT(type=INPUT_MOUSE)
    move.mi = MOUSEINPUT(dx=ax, dy=ay, mouseData=0,
                         dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                         time=0, dwExtraInfo=WISP_SIGNATURE)
    down_flag, up_flag = ((MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) if button == "right"
                          else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))
    clicks = []
    for _ in range(2 if double else 1):
        for flag in (down_flag, up_flag):
            item = INPUT(type=INPUT_MOUSE)
            item.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0,
                                 dwExtraInfo=WISP_SIGNATURE)
            clicks.append(item)
    return _send([move, *clicks])


def mouse_wheel(clicks: int) -> int:
    item = INPUT(type=INPUT_MOUSE)
    item.mi = MOUSEINPUT(dx=0, dy=0, mouseData=ctypes.c_uint32(clicks * WHEEL_DELTA).value,
                         dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=WISP_SIGNATURE)
    return _send([item])
