"""D-045: the island window: a fixed canvas that never resizes, springs driven by one frame
timer that stops when nothing moves, the click-through input region, never taking focus,
interaction (hover, hold, click, scroll, swipe, Esc, right-click), services reporting to it,
full-screen hiding and reduce motion."""

from __future__ import annotations

import ctypes
from itertools import pairwise
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QEnterEvent, QGuiApplication, QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QWidget

from wisp.system.media import MediaState
from wisp.ui import motion
from wisp.ui.island import geometry
from wisp.ui.island.spring import Spring
from wisp.ui.theme import ISLAND

pytestmark = pytest.mark.qt
FRAME = 1 / 60
PLAYING = MediaState(True, "Weightless", "Marconi Union", "Spotify", True, 95, 480)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeVoice(QObject):
    visual = Signal(str, float, str)
    transcript = Signal(str, str, bool, int)
    message = Signal(str)

    def __init__(self):
        super().__init__()
        self.mic = SimpleNamespace(muted=False)
        self.always_listening = False
        self.live_state = "ready"
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args: self.calls.append((name, *args))


class CountingTab(QWidget):
    def __init__(self):
        super().__init__()
        self.refreshes = 0

    def refresh(self):
        self.refreshes += 1


@pytest.fixture
def island(qtbot, isolated_data_dir):
    from wisp.ui.island.island import Island
    from wisp.ui.island.machine import IslandStateMachine

    clock = Clock()
    commands = []
    widget = Island(FakeVoice(), "#7c5cff", lambda: True, commands.append,
                    [("Today", CountingTab())], machine=IslandStateMachine(clock=clock))
    widget.clock = clock
    widget.wall = lambda: 1.8e9 + clock.now
    # The real pointer may rest where the island appears: no real mouse events in these tests
    # (handlers are called directly), and its timers never fire on their own.
    widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    for timer in (widget._hold, widget._leave, widget._outside, widget._poll):
        timer.setInterval(3_600_000)
    qtbot.addWidget(widget)
    qtbot.addWidget(widget.shadow)
    widget.commands, widget.fake = commands, clock
    return widget


def show(island) -> None:
    island.enabled = True
    island._apply_visibility()
    island._frame.stop()  # tests step frames themselves


def run(island, seconds: float) -> list[float]:
    heights = []
    for _ in range(round(seconds / FRAME)):
        island.fake.now += FRAME
        island._tick()
        heights.append(island._main.height())
    return heights


# ----- window ------------------------------------------------------------------------------------
def test_window_is_a_frameless_topmost_tool_window_shown_without_activating(island):
    flags = island.windowFlags()
    for flag in (Qt.WindowType.Tool, Qt.WindowType.FramelessWindowHint,
                 Qt.WindowType.WindowStaysOnTopHint):
        assert flags & flag
    assert island.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert island.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    shadow = island.shadow.windowFlags()
    assert shadow & Qt.WindowType.WindowTransparentForInput  # the shadow never takes clicks


@pytest.mark.windows
def test_native_styles_and_the_foreground_is_never_taken(island):
    from wisp.winapi import windows as win

    before = win.foreground_hwnd()
    motion.force(True)
    show(island)
    island.expand()
    run(island, 0.6)
    island.collapse()
    run(island, 0.6)
    style = win.ex_style(int(island.winId()))
    for bit in (0x08000000, 0x80, 0x8, 0x80000):  # NOACTIVATE, TOOLWINDOW, TOPMOST, LAYERED
        assert style & bit, hex(bit)
    assert win.foreground_hwnd() == before


def test_canvas_is_fixed_size_at_the_top_centre(island):
    show(island)
    assert (island.width(), island.height()) == geometry.canvas_size()
    screen = QGuiApplication.primaryScreen()
    assert abs(island.geometry().center().x() - screen.geometry().center().x()) <= 1
    assert island.y() == screen.availableGeometry().y()
    motion.force(True)
    island.expand()
    sizes = {island.size().toTuple() for _ in run(island, 0.5)}
    assert sizes == {geometry.canvas_size()}  # the native window never resizes


# ----- motion ------------------------------------------------------------------------------------
def test_expand_springs_with_a_small_overshoot_and_then_shows_the_live_panel(island):
    motion.force(True)
    show(island)
    island.expand()
    assert island.panel.isHidden()  # a snapshot morphs; the live panel comes when settled
    heights = run(island, 0.7)
    target = ISLAND.expanded[1]
    assert target < max(heights) <= target * 1.02  # a few pixels past, then back
    assert heights[-1] == target
    assert not island.panel.isHidden()
    assert island.frame_interval(island.fake.now) is None  # settled: the frame timer stops


def test_collapse_never_overshoots_and_interrupting_never_jumps(island):
    motion.force(True)
    show(island)
    island.expand()
    first = run(island, 0.1)
    island.collapse()  # mid-expansion
    second = run(island, 0.7)
    plain = Spring(float(ISLAND.idle[1]))
    plain.retarget(ISLAND.expanded[1], ISLAND.expand)
    plain_heights = [ISLAND.idle[1]]
    for _ in range(40):
        plain.step(FRAME)
        plain_heights.append(plain.value)

    def fastest(values):
        return max(abs(b - a) for a, b in pairwise(values))

    # Continuous: no frame moves further than an uninterrupted expand's fastest frame does.
    assert fastest([ISLAND.idle[1], *first, *second]) <= fastest(plain_heights) + 0.5
    assert second[0] >= first[-1] - 1  # momentum carries on for a moment
    assert min(second) >= ISLAND.idle[1] and second[-1] == ISLAND.idle[1]


def test_radius_stays_a_capsule_while_compact(island):
    motion.force(True)
    show(island)
    island.machine.set_voice("listening", "Listening…")
    for _ in run(island, 0.3):
        main = island._main
        assert geometry.corner_radius(main.height()) == main.height() / 2


def test_frame_timer_only_runs_while_something_moves(island):
    motion.force(True)
    show(island)
    run(island, 1.0)
    now = island.fake.now
    assert island.frame_interval(now) == ISLAND.idle_frame_ms  # the orb's slow glow
    island.machine.set_voice("listening")
    run(island, 1.0)
    assert island.frame_interval(island.fake.now) == 33
    island.machine.set_voice("idle")
    island.show_media(PLAYING)
    run(island, 1.0)
    assert island.frame_interval(island.fake.now) == ISLAND.meter_frame_ms
    motion.force(False)
    island.show_media(MediaState())
    run(island, 0.5)
    assert island.frame_interval(island.fake.now) is None  # idle with motion off: no timer
    island.hide()
    assert island.frame_interval(island.fake.now) is None


def test_reduce_motion_jumps_the_shape_and_crossfades_content(island):
    motion.force(False)
    show(island)
    island.expand()
    assert island._main.height() == ISLAND.expanded[1]  # no spring
    incoming = island._layers[-1]
    assert incoming.in_ms == ISLAND.crossfade_ms and incoming.scale_from == 1.0


def test_content_fades_and_scales_between_states(island):
    motion.force(True)
    show(island)
    island.machine.set_voice("listening")
    outgoing, incoming = island._layers[-2], island._layers[-1]
    now = island.fake.now
    assert outgoing.end == now and incoming.start > now  # incoming starts after the shape
    assert incoming.scale(incoming.start) == pytest.approx(ISLAND.content_scale)
    run(island, 0.4)
    assert island._layers == [incoming] and incoming.alpha(island.fake.now) == 1.0


# ----- click-through -----------------------------------------------------------------------------
@pytest.mark.windows
def test_clicks_beside_the_shape_reach_the_app_underneath(island, qtbot):
    from wisp.winapi import windows as win

    motion.force(False)
    show(island)
    hwnd = int(island.winId())
    # Another topmost window at the top centre (a running Wisp, say) would hide this one:
    # bring it to the top of the topmost group first, without activating it.
    ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0,
                                      0x0001 | 0x0002 | 0x0010)
    qtbot.wait(150)
    ratio = island.devicePixelRatioF()

    def owner(point: QPointF) -> int:
        native = island.mapToGlobal(point.toPoint())
        info = win.window_at(round(native.x() * ratio), round(native.y() * ratio))
        return info.hwnd if info else 0

    main = island._main
    cover = win.window_at(*(round(v * ratio) for v in island.mapToGlobal(
        main.center().toPoint()).toTuple()))
    if cover is not None and cover.hwnd != hwnd and (
            win.class_name(cover.hwnd) == "LockScreenBackstopFrame" or cover.process == "LockApp"):
        pytest.skip("the lock screen covers the desktop (it sits above every topmost window)")
    assert owner(main.center()) == hwnd
    beside = QPointF(main.right() + 20, main.center().y())
    below = QPointF(main.center().x(), main.bottom() + 60)
    assert owner(beside) != hwnd and owner(below) != hwnd
    island.expand()
    island._sync_mask()
    qtbot.wait(100)
    assert owner(below) == hwnd  # the input region follows the shape


# ----- interaction -------------------------------------------------------------------------------
def test_hover_grows_slightly_and_holding_expands(island, qtbot):
    motion.force(False)
    show(island)
    island._hold.setInterval(ISLAND.hover_hold_ms)
    island.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    assert island._main.width() == pytest.approx(ISLAND.idle[0] * ISLAND.hover_scale)
    assert island._hold.isActive()
    qtbot.waitUntil(lambda: island.machine.expanded, timeout=2000)


def test_scroll_down_expands_and_scroll_up_dismisses_a_banner(island):
    def wheel(dy: int, at: QPointF | None = None):
        at = at or QPointF(400, 20)
        return QWheelEvent(at, at, QPoint(0, 0), QPoint(0, dy), Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)

    show(island)
    island.wheelEvent(wheel(-120))
    assert island.machine.expanded
    island.wheelEvent(wheel(120, QPointF(island.panel.x() + 40, island.panel.y() + 20)))
    assert not island.machine.expanded  # scroll up on the island's top band
    island.machine.post("Reminder", "Call the bank")
    island.wheelEvent(wheel(120))
    assert island.presentation.mode == "idle"


def test_esc_collapses_and_dismisses(island):
    show(island)
    island.expand()
    island.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                   Qt.KeyboardModifier.NoModifier))
    assert not island.machine.expanded
    island.machine.post("Reminder", "Call the bank")
    island.escape()
    assert island.presentation.mode == "idle"


def click(island, x: float, y: float | None = None) -> None:
    point = QPointF(x, island._main.center().y() if y is None else y)
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        event = QMouseEvent(kind, point, point, Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        (island.mousePressEvent if kind == QEvent.Type.MouseButtonPress
         else island.mouseReleaseEvent)(event)


def test_compact_music_click_plays_or_pauses_without_expanding(island):
    motion.force(False)
    show(island)
    island.show_media(PLAYING)
    click(island, island._main.right() - 20)
    assert island.commands == ["play_pause"] and not island.machine.expanded
    click(island, island._main.center().x() - 30)
    assert island.machine.expanded  # elsewhere on the pill: expand


def test_orb_click_talks_and_banner_click_runs_its_action(island):
    motion.force(False)
    show(island)
    click(island, island._main.left() + 10)
    assert ("toggle_talk",) in island.voice.calls and not island.machine.expanded
    opened = []
    island.machine.post("Reminder", "Call the bank", action=lambda: opened.append(1))
    click(island, island._main.center().x())
    assert opened == [1] and island.presentation.mode == "idle"


def test_swipe_up_dismisses_a_banner(island):
    motion.force(False)
    show(island)
    island.machine.post("Routine done: Morning", "All good")
    start = QPointF(island._main.center())
    press = QMouseEvent(QEvent.Type.MouseButtonPress, start, start, Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    island.mousePressEvent(press)
    end = start - QPointF(0, 30)
    move = QMouseEvent(QEvent.Type.MouseMove, end, end, Qt.MouseButton.NoButton,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    island.mouseMoveEvent(move)
    assert island.presentation.mode == "idle"


def test_right_click_menu(island, qtbot):
    menu = island.context_menu()
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels == ["Settings…", "Mute microphone", "Open in window", "Quit Wisp"]
    with qtbot.waitSignal(island.quit_requested):
        menu.actions()[-1].trigger()
    menu.actions()[1].trigger()
    assert ("set_muted", True) in island.voice.calls


def test_text_box_click_takes_focus_and_collapse_gives_it_back(island, monkeypatch):
    from wisp.ui.island import island as module

    calls = []
    state = {"foreground": 111}
    monkeypatch.setattr(module.win, "foreground_hwnd", lambda: state["foreground"])

    def set_foreground(hwnd):
        calls.append(hwnd)
        state["foreground"] = hwnd
        return True

    monkeypatch.setattr(module.win, "set_foreground", set_foreground)
    show(island)
    island.expand()
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    island.eventFilter(island.panel.chat.input, press)  # a click into the text box
    assert calls == [int(island.winId())]
    island.collapse()
    assert calls == [int(island.winId()), 111]  # the app you were in gets focus back
    island.eventFilter(island.panel, press)  # clicks elsewhere never take focus
    assert len(calls) == 2


# ----- services ----------------------------------------------------------------------------------
def test_voice_messages_become_banners(island):
    island.voice.message.emit("Microphone muted.")
    assert island.presentation.banner.title == "Microphone muted."
    island.machine.dismiss()
    island.voice.live_state = "error"
    island.voice.message.emit("Google rejected this API key.")
    banner = island.presentation.banner
    assert (banner.title, banner.tone, banner.icon) == ("Voice problem", "danger", "error")
    banner.action()
    assert ("retry",) in island.voice.calls
    island.machine.dismiss()
    island.voice.live_state = "ready"
    island.machine.set_voice("listening")
    island.voice.message.emit("Listening — click Talk again to send.")
    island.machine.set_voice("idle")
    assert island.presentation.mode == "idle"  # a mid-turn hint never shows up late


def test_notifications_get_an_icon_and_open_the_right_tab(island):
    from wisp.ui.island.island import banner_style

    assert banner_style("Reminder") == ("calendar", "warning", "Today")
    assert banner_style("Routine done: Morning apps") == ("check", "success", "Today")
    assert banner_style("Missed while Wisp was closed")[1] == "warning"
    island.notify("Routine done: Morning apps", "✓ Opened Spotify\n✓ Opened Unity Hub")
    banner = island.presentation.banner
    assert banner.line == "✓ Opened Spotify"
    banner.action()
    assert island.machine.expanded and island.panel.stack.currentIndex() == 1  # Today


def test_speaking_shows_the_first_words_of_the_reply(island):
    island.voice.transcript.emit("model", "It's 3 pm and sunny.", False, 0)
    island.voice.visual.emit("speaking", 0.4, "Speaking")
    assert island.look.reply == "It's 3 pm and sunny."
    assert island.presentation.main.kind == "speaking"


def test_media_art_and_the_panel_strip(island):
    island.show_media(PLAYING)
    assert not island.panel.music.isHidden() and island.look.art is None  # no art bytes
    assert island.presentation.main.kind == "music"


def test_feedback_adapter_routes_dictation_to_the_island_or_the_hud(island):
    from wisp.ui.island.feedback import IslandFeedback

    hud = SimpleNamespace(calls=[], accent="#7c5cff")
    hud.show_state = lambda *a: hud.calls.append(("show_state", *a))
    hud.flash = lambda *a: hud.calls.append(("flash", *a))
    hud.hide_now = lambda: hud.calls.append(("hide_now",))
    feedback = IslandFeedback(island, hud)
    island.enabled = True
    feedback.show_state("Dictating… release to insert", "success", lambda: 0.3)
    main = island.presentation.main
    assert (main.kind, main.tone, main.meter) == ("dictation", "success", "dictation")
    feedback.flash("Inserted 12 words", 1500, "success")
    assert island.presentation.main.kind == "status"
    feedback.flash("Couldn't reach Google", 4000, "danger")
    assert island.presentation.banner.tone == "danger"
    island.enabled = False
    feedback.flash("Inserted 3 words", 1500, "success")
    assert hud.calls == [("flash", "Inserted 3 words", 1500, "success")]


def test_circle_answer_becomes_a_banner_that_opens_chat(island):
    from wisp.ui.island.feedback import IslandBubble

    bubble = SimpleNamespace(calls=[])
    bubble.show_at = lambda *a: bubble.calls.append("show_at")
    island.enabled = True
    adapter = IslandBubble(island, bubble)
    adapter.show_at(QPoint(10, 10), "…")
    adapter.set_text("A red maple leaf. It's the Canadian flag's emblem.")
    adapter.finish(12.0)
    banner = island.presentation.banner
    assert (banner.title, banner.line) == ("Answer", "A red maple leaf")
    banner.action()
    assert island.machine.expanded and island.panel.stack.currentIndex() == 0  # Chat
    assert bubble.calls == []


def test_full_screen_apps_hide_the_island(island, monkeypatch):
    from wisp.ui.island import island as module

    covered = {"value": True}
    monkeypatch.setattr(module.fullscreen, "fullscreen_over", lambda hwnd: covered["value"])
    show(island)
    island.expand()
    island._poll_environment()
    assert island.presentation.mode == "hidden" and not island.isVisible()
    assert not island.machine.expanded and not island.shadow.isVisible()
    covered["value"] = False
    island._poll_environment()
    assert island.isVisible() and island.presentation.mode == "idle"


def test_switched_off_island_stays_hidden(island):
    island.set_enabled(False)
    assert not island.isVisible() and not island._poll.isActive()
    island.machine.set_voice("listening")
    assert not island.isVisible()


def test_panel_has_chat_first_and_open_in_window(island):
    names = [name for name, _widget in island.panel.tabs]
    assert names[0] == "Chat" and "Today" in names
    with pytest.raises(AssertionError):
        assert island.panel.open_window.isHidden()
    island.voice.transcript.emit("user", "What time is it?", True, 1)
    assert island.panel.chat.view.rows()[0].text == "What time is it?"
    island.open_tab("Today")
    assert island.machine.expanded and island.panel.tabs[1][1].refreshes >= 1


def test_esc_watch_follows_expansion():
    """The keyboard hook reports Esc (never swallowing it) only while asked to."""
    import ctypes

    from wisp.hotkeys import hook as hook_module

    events = []
    keyboard = hook_module.KeyboardHook(emit=lambda name, kind: events.append((name, kind)))
    keyboard.configure({}, 250)
    info = hook_module.KBDLLHOOKSTRUCT(vkCode=hook_module.VK_ESCAPE)
    pointer = ctypes.addressof(info)
    keyboard._hook_proc(hook_module.HC_ACTION, hook_module.WM_KEYDOWN, pointer)
    assert events == []
    keyboard.watch_escape = True
    result = keyboard._hook_proc(hook_module.HC_ACTION, hook_module.WM_KEYDOWN, pointer)
    assert events == [("escape", "press")] and result != 1  # passed on, not swallowed
