"""Windows integration: real UI Automation, window APIs and screen capture against a test window
that the test creates itself (no external apps are opened)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

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


def _uia_client(hwnd: int, action: str, qtbot) -> dict:
    """Run the UIA client in a child process while this process keeps pumping Qt events."""
    probe = Path(__file__).with_name("uia_client_probe.py")
    proc = subprocess.Popen([sys.executable, str(probe), str(hwnd), action],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    qtbot.waitUntil(lambda: proc.poll() is not None, timeout=30000)
    out, err = proc.communicate()
    assert proc.returncode == 0, err
    return json.loads(out.strip().splitlines()[-1])


def test_uia_click_and_type(probe_window, qtbot):
    result = _uia_client(int(probe_window.winId()), "click_and_type", qtbot)
    assert "limit" not in result, result
    assert "Probe Action" in result["names"]
    qtbot.waitUntil(lambda: probe_window.clicks == [1], timeout=5000)
    qtbot.waitUntil(lambda: probe_window.field.text() == "hello wisp", timeout=5000)
    assert result["how"] in ("invoked", "default action")
    assert result["typed"] in ("set", "typed")


def test_uia_reports_missing_element(probe_window, qtbot):
    result = _uia_client(int(probe_window.winId()), "missing", qtbot)
    assert "couldn't find" in result["limit"]


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
