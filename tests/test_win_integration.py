"""Windows integration: real UI Automation, window APIs and screen capture against a test window
that the test creates itself (no external apps are opened)."""

from __future__ import annotations

import io
import threading

import pytest

pytestmark = [pytest.mark.windows, pytest.mark.qt]


@pytest.fixture
def probe_window(qtbot):
    from PySide6.QtWidgets import QLineEdit, QPushButton, QVBoxLayout, QWidget

    window = QWidget()
    window.setWindowTitle("Wisp UIA Probe")
    layout = QVBoxLayout(window)
    button = QPushButton("Probe Action")
    field = QLineEdit()
    field.setAccessibleName("Probe Field")
    layout.addWidget(button)
    layout.addWidget(field)
    window.resize(360, 160)
    clicks: list[int] = []
    button.clicked.connect(lambda: clicks.append(1))
    window.show()
    qtbot.waitExposed(window)
    window.clicks = clicks
    window.field = field
    yield window
    window.close()


def _in_mta(fn, qtbot) -> dict:
    result: dict = {}

    def worker() -> None:
        import pythoncom

        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        try:
            result["value"] = fn()
        except Exception as exc:
            result["error"] = repr(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    qtbot.waitUntil(lambda: not thread.is_alive(), timeout=20000)
    return result


def test_uia_click_and_type(probe_window, qtbot):
    from wisp.winapi.uia import Uia

    hwnd = int(probe_window.winId())

    def run():
        uia = Uia()
        names = [e["name"] for e in uia.list_elements(hwnd)]
        how = uia.click(uia.find(hwnd, "Probe Action"))
        typed = uia.type_into(uia.find(hwnd, "Probe Field", editable=True), "hello wisp")
        return names, how, typed

    result = _in_mta(run, qtbot)
    assert "error" not in result, result.get("error")
    names, how, typed = result["value"]
    assert "Probe Action" in names
    qtbot.waitUntil(lambda: probe_window.clicks == [1], timeout=5000)
    qtbot.waitUntil(lambda: probe_window.field.text() == "hello wisp", timeout=5000)
    assert how in ("invoked", "default action") and typed in ("set", "typed")


def test_uia_reports_missing_element(probe_window, qtbot):
    from wisp.winapi.uia import Uia, UiaLimit

    hwnd = int(probe_window.winId())

    def run():
        try:
            Uia().find(hwnd, "Nonexistent Fancy Control")
        except UiaLimit as exc:
            return str(exc)
        return "found"

    result = _in_mta(run, qtbot)
    assert "couldn't find" in result["value"]


def test_window_bounds_minimize_restore(probe_window, qtbot):
    from wisp.winapi import windows

    hwnd = int(probe_window.winId())
    left, top, right, bottom = windows.frame_bounds(hwnd)
    assert right - left >= 300 and bottom - top >= 100
    assert windows.is_window(hwnd)
    windows.minimize(hwnd)
    qtbot.waitUntil(probe_window.isMinimized, timeout=5000)
    windows.restore(hwnd)
    qtbot.waitUntil(lambda: not probe_window.isMinimized(), timeout=5000)
    assert windows.input_desktop_available()
    assert all(w.pid != 0 for w in windows.list_windows())


def test_screen_capture_of_window(probe_window, qtbot):
    from PIL import Image

    from wisp.winapi import screen, windows

    region = screen.clamp_to_screens(windows.frame_bounds(int(probe_window.winId())))
    shot = screen.capture(region)
    image = Image.open(io.BytesIO(shot.jpeg))
    assert image.format == "JPEG"
    assert max(image.size) <= screen.MAX_EDGE
    assert shot.width >= 300
    full = screen.capture(screen.monitors()[0])
    assert max(Image.open(io.BytesIO(full.jpeg)).size) <= screen.MAX_EDGE
