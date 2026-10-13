"""Dev helper: idle CPU of Wisp (Island visible, console hidden, no key, throwaway data folder).

Run: .venv\\Scripts\\python spikes\\idle_cpu.py [seconds]
Starts ``python -m wisp --background``, waits 15 s, then measures the CPU time (GetProcessTimes,
kernel + user) of the whole process tree over the window — a venv's python.exe is a launcher
that runs the real interpreter as a child — and reports it as % of one core.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.restype = wintypes.HANDLE


def cpu_seconds(handle) -> float:
    created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
    if not _kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                     ctypes.byref(kernel), ctypes.byref(user)):
        raise OSError(ctypes.get_last_error())

    def as_seconds(ft: wintypes.FILETIME) -> float:
        return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7

    return as_seconds(kernel) + as_seconds(user)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


def process_tree(root: int) -> list[int]:
    """``root`` and all its descendants (Tool Help snapshot)."""
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = _kernel32.CreateToolhelp32Snapshot(0x2, 0)
    parents: dict[int, int] = {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    ok = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
    while ok:
        parents[entry.th32ProcessID] = entry.th32ParentProcessID
        ok = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    _kernel32.CloseHandle(snapshot)
    tree, changed = {root}, True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in tree and pid not in tree:
                tree.add(pid)
                changed = True
    return sorted(tree)


def main() -> None:
    numbers = [a for a in sys.argv[1:] if not a.startswith("--")]
    window = float(numbers[0]) if numbers else 60.0
    data = tempfile.mkdtemp(prefix="wisp-idle-")
    if "--reduce-motion" in sys.argv:
        with open(os.path.join(data, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"loadout": {"reduce_motion": True}}, f)
    env = dict(os.environ, WISP_DATA_DIR=data)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    proc = subprocess.Popen([pythonw if os.path.exists(pythonw) else sys.executable, "-m", "wisp",
                             "--background"], env=env)
    try:
        time.sleep(15)
        handles = [_kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                   for pid in process_tree(proc.pid)]
        handles = [h for h in handles if h]
        start_cpu, start = sum(map(cpu_seconds, handles)), time.monotonic()
        time.sleep(window)
        used = sum(map(cpu_seconds, handles)) - start_cpu
        elapsed = time.monotonic() - start
        for handle in handles:
            _kernel32.CloseHandle(handle)
        print(f"idle CPU over {elapsed:.0f} s ({len(handles)} processes): {used:.2f} s CPU = "
              f"{100 * used / elapsed:.2f} % of one core")
    finally:
        proc.terminate()
        proc.wait(10)


if __name__ == "__main__":
    main()
