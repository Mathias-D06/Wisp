"""Running-process names via the documented Tool Help snapshot (CreateToolhelp32Snapshot with
TH32CS_SNAPPROCESS "includes all processes in the system"; Process32FirstW/NextW read
PROCESSENTRY32W.szExeFile; the snapshot is closed with CloseHandle). No process is opened, so
services we couldn't query with OpenProcess are listed too.

Used only to recognise anti-cheat clients (DECISIONS.md D-035): Wisp then refuses raw input
into a full-screen window rather than risk a game treating injected input as cheating.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH = 260

# Executable names (lower case, without .exe) of common anti-cheat clients.
ANTI_CHEAT = {
    "easyanticheat": "Easy Anti-Cheat", "easyanticheat_eos": "Easy Anti-Cheat",
    "beservice": "BattlEye", "beservice_x64": "BattlEye",
    "vgc": "Riot Vanguard", "vgtray": "Riot Vanguard",
    "faceit": "FACEIT", "faceitservice": "FACEIT",
    "eaanticheat.gameservice": "EA Javelin", "pnkbstra": "PunkBuster", "pnkbstrb": "PunkBuster",
    "gamemon": "nProtect GameGuard", "gamemon64": "nProtect GameGuard",
    "xigncode": "XIGNCODE3", "ace-tray": "Anti-Cheat Expert", "sguard64": "Anti-Cheat Expert",
}


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * MAX_PATH)]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.Process32NextW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def running_names() -> set[str]:
    """Lower-case executable names (without .exe) of all running processes."""
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return set()
    names: set[str] = set()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile.lower()
            names.add(name[:-4] if name.endswith(".exe") else name)
            ok = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snapshot)
    return names


def anti_cheat_running(names: set[str] | None = None) -> list[str]:
    """Product names of anti-cheat clients that are running (empty if none)."""
    found = (names if names is not None else running_names()) & ANTI_CHEAT.keys()
    return sorted({ANTI_CHEAT[name] for name in found})
