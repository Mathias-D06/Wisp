"""Low-level keyboard hook (WH_KEYBOARD_LL) on a dedicated thread with its own message loop.

Sources: SetWindowsHookExW, LowLevelKeyboardProc, KBDLLHOOKSTRUCT (learn.microsoft.com).
The hook procedure must return quickly (Windows silently removes hooks that exceed
LowLevelHooksTimeout, max 1 s), so it only updates the in-memory ChordMachine; events are
delivered to the app through a callback that must not block (Qt queued signals).
"""

from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes

from wisp.hotkeys.chords import Chord, ChordMachine
from wisp.winapi import input as winput

log = logging.getLogger(__name__)

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10
VK_ESCAPE = 0x1B  # Virtual-Key Codes (learn.microsoft.com)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = LRESULT
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                wintypes.UINT]
_user32.GetMessageW.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM]
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class KeyboardHook:
    """Owns the hook thread and a ChordMachine for the configured chords."""

    def __init__(self, emit: Callable[[str, str], None]):
        self._emit = emit
        self._machine: ChordMachine | None = None
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._hook = None
        self._proc = HOOKPROC(self._hook_proc)  # keep a reference for the hook's lifetime
        self._ready = threading.Event()
        self.error: str | None = None
        self.paused = False
        self.watch_escape = False  # report Esc (never swallowed) while the island is expanded

    def configure(self, chords: dict[str, Chord], hold_ms: int) -> None:
        self._machine = ChordMachine(
            chords=chords,
            hold_ms=hold_ms,
            emit=self._emit,
            schedule=_schedule,
            on_activate=lambda chord: winput.send_mask_key(),
            replay_key=lambda vk: winput.tap(vk),
        )

    def start(self) -> bool:
        if self._thread is not None:
            return True
        self._thread = threading.Thread(target=self._run, name="keyboard-hook", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        return self.error is None

    def stop(self) -> None:
        if self._thread is None:
            return
        _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(2)
        self._thread = None

    def _run(self) -> None:
        self._thread_id = _kernel32.GetCurrentThreadId()
        module = _kernel32.GetModuleHandleW(None)
        self._hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, module, 0)
        if not self._hook:
            self.error = f"SetWindowsHookExW failed (error {ctypes.get_last_error()})"
            log.error(self.error)
            self._ready.set()
            return
        log.info("Keyboard hook installed")
        self._ready.set()
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            continue
        _user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        log.info("Keyboard hook removed")

    def _hook_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code == HC_ACTION and self._machine is not None and not self.paused:
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                ours = (info.flags & LLKHF_INJECTED) and info.dwExtraInfo == winput.WISP_SIGNATURE
                if not ours:
                    down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    if down and self.watch_escape and info.vkCode == VK_ESCAPE:
                        self._emit("escape", "press")
                    if self._machine.key_event(int(info.vkCode), down):
                        return 1
            except Exception:
                log.exception("Hook procedure error")
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)


def _schedule(delay: float, fn: Callable[[], None]) -> threading.Timer:
    timer = threading.Timer(delay, fn)
    timer.daemon = True
    timer.start()
    return timer
