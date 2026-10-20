"""D-056: what Screen Assist captures when the window in front can't be captured. The desktop,
a taskbar, a cloaked or empty window (DWM reported 0,0,0,0 in the bug), an off-screen window
or Wisp's own window: the next real window in z-order is used, or the whole monitor under the
pointer, and the card says so. Rectangles are clamped to the virtual screen. Fake windows only;
the last test reads real window rectangles (no image is taken)."""

from __future__ import annotations

import ctypes

import pytest

from tests.test_screen_assist import CODE, FakeModel, FakeSystem, Window, capturer, editor
from wisp.assist.engine import (
    WHOLE_SCREEN_NOTE,
    AssistEngine,
    Blocked,
    CaptureError,
    Capturer,
    clamp,
    valid_rect,
)
from wisp.assist.privacy import Blocklist

SCREEN = (0, 0, 1600, 1000)


class Desk(FakeSystem):
    """FakeSystem with window classes, cloaking, a virtual screen and a pointer."""

    def __init__(self, front, others=(), bounds=None, classes=None, cloaked=(),
                 virtual=SCREEN, cursor=(800, 500)):
        super().__init__(front, {}, others=list(others))
        self.bounds_of.update(bounds or {})
        self.classes = classes or {}
        self.hidden = set(cloaked)
        self.virtual = virtual
        self.pointer = cursor

    def system(self):
        system = super().system()
        system.class_name = lambda hwnd: self.classes.get(hwnd, "")
        system.cloaked = lambda hwnd: hwnd in self.hidden
        system.virtual_screen = lambda: self.virtual
        system.cursor = lambda: self.pointer
        return system


EDITOR = Window(3, "main.py - Code", "Code")
NOTES = Window(4, "notes.txt - Notepad", "notepad")


def shot_of(desk: Desk, **kwargs):
    return capturer(desk).capture(**kwargs)


# ----- rectangles ---------------------------------------------------------------------------------
def test_empty_and_negative_rectangles_are_invalid():
    assert not valid_rect(None)
    assert not valid_rect((0, 0, 0, 0))  # what DWM reported in the bug
    assert not valid_rect((10, 10, 10, 50))
    assert not valid_rect((10, 10, 5, 50))
    assert valid_rect((0, 0, 1, 1))


def test_rectangles_are_clamped_to_the_virtual_screen():
    assert clamp((-8, -8, 1608, 1008), SCREEN) == SCREEN  # a maximised window's borders
    assert clamp((1500, 900, 1900, 1300), SCREEN) == (1500, 900, 1600, 1000)
    assert clamp((2000, 0, 2400, 400), SCREEN) is None  # wholly off-screen
    assert clamp((1596, 0, 1700, 400), SCREEN) is None  # 4 px showing: not worth a look


# ----- choosing the window ------------------------------------------------------------------------
def test_an_empty_window_in_front_is_skipped_for_the_next_one():
    ghost = Window(7, "", "explorer")
    desk = Desk(ghost, [EDITOR], bounds={7: (0, 0, 0, 0)})
    shot = shot_of(desk)
    assert shot.hwnd == 3 and desk.grabs == [(0, 0, 1600, 1000)]
    assert shot.note == "The window in front can't be captured, so I looked at “main.py - Code”."


@pytest.mark.parametrize("cls", ["Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"])
def test_the_desktop_and_taskbars_are_skipped(cls):
    shell = Window(8, "Program Manager", "explorer")
    desk = Desk(shell, [EDITOR], classes={8: cls})
    assert shot_of(desk).hwnd == 3


def test_cloaked_and_minimised_windows_are_skipped():
    cloaked = Window(5, "Settings", "SystemSettings")
    small = Window(6, "Calculator", "CalculatorApp", minimized=True)
    desk = Desk(cloaked, [small, EDITOR], cloaked={5})
    assert shot_of(desk).hwnd == 3


def test_an_off_screen_window_is_skipped_and_a_partly_visible_one_clamped():
    away = Window(5, "Old dialog", "app")
    desk = Desk(away, [EDITOR], bounds={5: (3000, 0, 3400, 300), 3: (1200, 700, 2200, 1500)})
    shot = shot_of(desk)
    assert shot.hwnd == 3 and desk.grabs == [(1200, 700, 1600, 1000)]  # never past the screen


def test_wisps_own_window_is_skipped_for_the_next_real_window():
    own = Window(9, "Wisp Island", "Wisp", pid=1)
    desk = Desk(own, [NOTES, EDITOR])
    shot = shot_of(desk)
    assert shot.hwnd == 4 and "“notes.txt - Notepad”" in shot.note


def test_the_next_window_skips_blocked_ones_without_refusing():
    shell = Window(8, "", "explorer")
    bank = Window(5, "Bitwarden", "Bitwarden")
    desk = Desk(shell, [bank, EDITOR], classes={8: "WorkerW"})
    shot = shot_of(desk)
    assert shot.hwnd == 3  # the password manager was passed over, not captured or refused


def test_a_blocked_window_in_front_is_still_refused():
    bank = Window(5, "Bitwarden", "Bitwarden")
    with pytest.raises(Blocked):
        shot_of(Desk(bank, [EDITOR]))


def test_no_window_at_all_means_the_whole_monitor_under_the_pointer():
    shell = Window(8, "Program Manager", "explorer")
    desk = Desk(shell, [Window(6, "Calc", "calc", minimized=True)], classes={8: "Progman"},
                cursor=(1700, 300))
    desk.screen = (1600, 0, 3520, 1080)  # the monitor under the pointer
    desk.virtual = (0, 0, 3520, 1080)
    shot = shot_of(desk)
    assert (shot.target, shot.hwnd, shot.title) == ("screen", 0, "")
    assert shot.note == WHOLE_SCREEN_NOTE and desk.grabs == [(1600, 0, 3520, 1080)]
    assert shot.what == "the screen"


def test_the_whole_screen_note_reaches_the_card():
    from wisp.ui.island.assist_tab import transcript_markdown

    desk = Desk(None, [], cursor=(10, 10))
    engine = AssistEngine(FakeModel(["The desktop shows three folders."]), capturer(desk),
                          lambda: "English (UK)")
    exchange = engine.ask()
    assert exchange.notes == [WHOLE_SCREEN_NOTE]
    markdown = transcript_markdown([exchange])  # the note in italics, before the answer
    assert markdown.index("*I looked at the whole screen") < markdown.index("three folders")


def test_a_secure_desktop_is_still_an_error():
    desk = Desk(EDITOR)
    system = desk.system()
    system.desktop_available = lambda: False
    with pytest.raises(CaptureError):
        Capturer(system, Blocklist, own_pid=1).capture()


def test_blocked_windows_with_empty_rectangles_are_not_masked():
    bank = Window(5, "Bitwarden", "Bitwarden")
    desk = Desk(EDITOR, [bank], bounds={5: (0, 0, 0, 0)})
    shot = shot_of(desk, target="screen")
    assert shot.masked == 0 and shot.hwnd == 3


# ----- the Windows calls --------------------------------------------------------------------------
class FakeDll:
    def __init__(self, **functions):
        self.__dict__.update(functions)


def fill(ref, rect):
    target = ref._obj  # the RECT behind ctypes.byref(...)
    target.left, target.top, target.right, target.bottom = rect


@pytest.mark.windows
def test_frame_bounds_falls_back_to_getwindowrect(monkeypatch):
    from wisp.winapi import windows

    calls = []
    dwm_result = {"value": (0, 0, 0, 0), "status": 0}

    def dwm(hwnd, attribute, ref, size):
        fill(ref, dwm_result["value"])
        return dwm_result["status"]

    def window_rect(hwnd, ref):
        calls.append(hwnd)
        fill(ref, (10, 20, 810, 620))
        return 1

    monkeypatch.setattr(windows, "_dwmapi", FakeDll(DwmGetWindowAttribute=dwm))
    monkeypatch.setattr(windows, "_user32", FakeDll(GetWindowRect=window_rect))
    assert windows.frame_bounds(42) == (10, 20, 810, 620)  # DWM said 0,0,0,0
    dwm_result.update(status=-2147024809)  # E_INVALIDARG: DWM failed
    assert windows.frame_bounds(42) == (10, 20, 810, 620)
    dwm_result.update(value=(100, 100, 500, 400), status=0)
    assert windows.frame_bounds(42) == (100, 100, 500, 400) and calls == [42, 42]

    def empty_rect(hwnd, ref):
        fill(ref, (0, 0, 0, 0))
        return 1

    dwm_result.update(value=(0, 0, 0, 0))
    monkeypatch.setattr(windows, "_user32", FakeDll(GetWindowRect=empty_rect))
    assert windows.frame_bounds(42) is None  # never an empty rectangle


@pytest.mark.windows
def test_real_window_rectangles_are_never_empty():
    """Reads the rectangles of this PC's windows (no image is taken)."""
    from wisp.winapi import windows

    for window in windows.list_windows():
        bounds = windows.frame_bounds(window.hwnd)
        assert bounds is None or valid_rect(bounds)
    assert ctypes.sizeof(ctypes.c_void_p) == 8


def test_a_drawn_editor_is_still_a_plain_capture():
    desk = Desk(EDITOR)
    desk.images = {3: editor(CODE)}
    shot = shot_of(desk)
    assert shot.note == "" and shot.target == "window" and shot.hwnd == 3
