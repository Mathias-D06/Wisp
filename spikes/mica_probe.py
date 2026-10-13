"""Spike: does DWMWA_SYSTEMBACKDROP_TYPE (Mica) look right on a Qt window?

(a) solid client area + dark title + rounded corners + Mica (title bar only shows it)
(b) client area left transparent + DwmExtendFrameIntoClientArea(-1) so Mica shows through
Both windows are shown for a moment and their on-screen pixels (only their own rectangles) are
captured to spikes/out/mica_a.png and mica_b.png.

Run: .venv\\Scripts\\python spikes\\mica_probe.py
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QVBoxLayout, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from wisp.winapi import dwm, screen, windows

OUT = Path(__file__).parent / "out"


class MARGINS(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int), ("top", ctypes.c_int),
                ("bottom", ctypes.c_int)]


def build(title: str, transparent: bool) -> QWidget:
    window = QWidget()
    window.setWindowTitle(title)
    window.resize(460, 260)
    if transparent:
        window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        window.setStyleSheet("QWidget#root { background: transparent; }")
    else:
        window.setStyleSheet("QWidget#root { background: #0e0f13; }")
    window.setObjectName("root")
    layout = QVBoxLayout(window)
    text = QLabel("Wisp — the quick brown fox jumps over the lazy dog 0123456789")
    text.setStyleSheet("color: #ecedf1; font-family: 'Segoe UI Variable Text'; font-size: 13px;")
    card = QFrame()
    card.setStyleSheet("QFrame { background: #16181d; border: 1px solid rgba(255,255,255,0.08);"
                       " border-radius: 12px; }")
    inner = QVBoxLayout(card)
    inner.addWidget(QLabel("Card text on a solid surface",
                           styleSheet="color: #ecedf1; border: none; font-size: 13px;"))
    inner.addWidget(QLineEdit(placeholderText="Type a request"))
    layout.addWidget(text)
    layout.addWidget(card)
    return window


def main() -> None:
    app = QApplication(sys.argv[:1])
    OUT.mkdir(exist_ok=True)
    print("build", dwm.windows_build())
    for name, transparent in (("a", False), ("b", True)):
        window = build(f"Mica probe {name}", transparent)
        window.move(200, 200)
        window.show()
        hwnd = int(window.winId())
        print(name, dwm.style_window(hwnd, dark=True))
        if transparent:
            ctypes.WinDLL("dwmapi").DwmExtendFrameIntoClientArea(
                wintypes.HWND(hwnd), ctypes.byref(MARGINS(-1, -1, -1, -1)))
        end = time.monotonic() + 1.5
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        bounds = windows.frame_bounds(hwnd)
        shot = screen.grab(bounds)
        shot.save(OUT / f"mica_{name}.png")
        window.close()
    print("saved", OUT / "mica_a.png", OUT / "mica_b.png")


if __name__ == "__main__":
    main()
