"""Spike: can a no-activate island give keyboard focus to its text box on demand? (D-045)

A: Qt's WindowDoesNotAcceptFocus flag (Qt sets WS_EX_NOACTIVATE) + SetForegroundWindow.
B: no Qt focus flag; WS_EX_NOACTIVATE set with SetWindowLongPtrW after creation, then
   SetForegroundWindow.
For each: is the window active, does the line edit have focus, and was the foreground window
left alone when the window was shown? No keys or clicks are sent.
Run: .venv\\Scripts\\python spikes\\island_focus_probe.py
"""

from __future__ import annotations

import ctypes
import sys
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

user32 = ctypes.WinDLL("user32")
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def probe(app, qt_flag: bool) -> None:
    flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint \
        | Qt.WindowType.WindowStaysOnTopHint
    if qt_flag:
        flags |= Qt.WindowType.WindowDoesNotAcceptFocus
    window = QWidget(None, flags)
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.resize(300, 80)
    edit = QLineEdit()
    QVBoxLayout(window).addWidget(edit)
    hwnd = int(window.winId())
    if not qt_flag:
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
    before = user32.GetForegroundWindow()
    window.move(40, 40)
    window.show()
    pump(app, 0.3)
    left_alone = user32.GetForegroundWindow() == before
    ok = bool(user32.SetForegroundWindow(hwnd))
    edit.setFocus()
    pump(app, 0.3)
    print(f"{'A Qt flag' if qt_flag else 'B Win32 style'}: shown without activating={left_alone}"
          f" SetForegroundWindow={ok} foreground={user32.GetForegroundWindow() == hwnd}"
          f" active={window.isActiveWindow()} edit focus={edit.hasFocus()}"
          f" noactivate style="
          f"{bool(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_NOACTIVATE)}")
    if before:
        user32.SetForegroundWindow(ctypes.c_void_p(before))  # give the user's window back
    pump(app, 0.2)
    window.close()


def main() -> None:
    app = QApplication(sys.argv[:1])
    probe(app, qt_flag=True)
    probe(app, qt_flag=False)


if __name__ == "__main__":
    main()
