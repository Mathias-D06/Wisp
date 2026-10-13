"""Spike: does a fixed transparent canvas window behave like the island needs on this PC?

Checks (D-045):
* the Qt flags/attributes give WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_LAYERED;
* showing it doesn't change the foreground window;
* with a mask (QWindow.setMask → SetWindowRgn) a point outside the shape is not ours
  (WindowFromPoint), a point inside is, and the shape still draws (pixels inside the shape only);
* without a mask, alpha-0 pixels of the layered window let the mouse through (documented);
* a WindowTransparentForInput window is never hit;
* how long a per-frame setMask takes.

Only pixels inside Wisp's own opaque shape are read from the screen.
Run: .venv\\Scripts\\python spikes\\island_window_probe.py
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QRegion
from PySide6.QtWidgets import QApplication, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

GWL_EXSTYLE = -20
STYLES = {"NOACTIVATE": 0x08000000, "TOOLWINDOW": 0x80, "TOPMOST": 0x8, "LAYERED": 0x80000,
          "TRANSPARENT": 0x20, "APPWINDOW": 0x40000}
user32 = ctypes.WinDLL("user32")
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetForegroundWindow.restype = ctypes.c_void_p


class Canvas(QWidget):
    PILL = QRect(210, 0, 180, 32)

    def __init__(self, transparent_for_input: bool = False):
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        if transparent_for_input:
            flags |= Qt.WindowType.WindowTransparentForInput
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(600, 300)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.PILL, 16, 16)
        painter.fillPath(path, QColor(0, 0, 0))
        painter.end()


def ex_style(widget: QWidget) -> list[str]:
    value = user32.GetWindowLongPtrW(int(widget.winId()), GWL_EXSTYLE)
    return [name for name, bit in STYLES.items() if value & bit]


def pump(app: QApplication, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def main() -> None:
    app = QApplication(sys.argv[:1])
    from wisp.winapi import screen, windows

    area = QGuiApplication.primaryScreen().geometry()
    dpr = QGuiApplication.primaryScreen().devicePixelRatio()
    before = user32.GetForegroundWindow()
    canvas = Canvas()
    canvas.move(area.x() + (area.width() - canvas.width()) // 2, area.y())
    canvas.show()
    pump(app, 0.4)
    hwnd = int(canvas.winId())
    print("ex-style:", ex_style(canvas))
    print("foreground unchanged after show:", user32.GetForegroundWindow() == before)

    def physical(x: int, y: int) -> tuple[int, int]:
        global_point = canvas.mapToGlobal(canvas.rect().topLeft())
        return round((global_point.x() + x) * dpr), round((global_point.y() + y) * dpr)

    inside = physical(Canvas.PILL.center().x(), Canvas.PILL.center().y())
    beside = physical(Canvas.PILL.right() + 20, 10)
    below = physical(300, 200)

    def ours(point) -> bool:
        info = windows.window_at(*point)
        return info is not None and info.hwnd == hwnd

    print("no mask: inside ours", ours(inside), "| beside ours", ours(beside),
          "| below ours", ours(below))
    region = QRegion(Canvas.PILL.adjusted(-1, -1, 1, 1), QRegion.RegionType.Ellipse) \
        .united(QRegion(Canvas.PILL.adjusted(15, -1, -15, 1)))
    canvas.windowHandle().setMask(region)
    pump(app, 0.3)
    print("mask: inside ours", ours(inside), "| beside ours", ours(beside),
          "| below ours", ours(below))
    if ours(inside):
        x, y = inside
        pixel = screen.grab((x - 2, y - 2, x + 2, y + 2)).getpixel((2, 2))
        print("pixel at the pill centre (expect black):", pixel)
    start = time.perf_counter()
    for i in range(120):
        canvas.windowHandle().setMask(QRegion(QRect(200 - i % 40, 0, 200 + 2 * (i % 40), 40)))
    print(f"setMask: {(time.perf_counter() - start) / 120 * 1000:.3f} ms per call")
    canvas.windowHandle().setMask(QRegion())
    ghost = Canvas(transparent_for_input=True)
    ghost.move(canvas.pos())
    ghost.show()
    pump(app, 0.3)
    ghost_hwnd = int(ghost.winId())
    print("ghost ex-style:", ex_style(ghost))
    info = windows.window_at(*inside)
    print("ghost hit at pill centre:", info is not None and info.hwnd == ghost_hwnd)
    print("foreground still unchanged:", user32.GetForegroundWindow() == before)
    ghost.close()
    canvas.close()


if __name__ == "__main__":
    main()
