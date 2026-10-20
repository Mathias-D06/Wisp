"""D-052 in the app: the Screen tab, the hotkey (capture on press, spoken question, tap for a
quick look), reading aloud, Insert only on a click, the voice tools, Watch mode's indicator,
the blocklist in look_at_screen and Circle to Ask, and the settings (with the Island hotkey
moving to Ctrl+Alt+I)."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from tests.test_island_window import island  # noqa: F401  (the island fixture)
from tests.test_screen_assist import CODE, FakeModel, FakeSystem, Window, capturer, editor
from wisp.assist.engine import AssistEngine, Blocked, Exchange, Shot
from wisp.assist.privacy import REFUSAL, Blocklist
from wisp.settings import Settings, validate
from wisp.tools.base import Origin, ToolContext, ToolError

pytestmark = pytest.mark.qt


class FakeMic:
    def __init__(self, audio: bytes = b""):
        self.audio = audio
        self.level = 0.0
        self.users = []

    def acquire(self, user):
        self.users.append(user)

    def subscribe(self, name, callback):
        callback(self.audio)

    def unsubscribe(self, name):
        pass

    def release(self, user):
        self.users.remove(user)


class FakePlayer:
    def __init__(self):
        self.fed = []

    def feed(self, pcm, force=False):
        self.fed.append(pcm)

    def is_playing(self):
        return False

    def clear(self):
        pass


def make_assist(images=None, front=None, answers=None, speak=True, audio=b"", speech=False,
                mic_silence=lambda pcm: None, held=0.0):
    """``held``: how long the hotkey stays down between press() and release() (seconds)."""
    from wisp.assist.service import ScreenAssist

    front = front or Window(1, "main.py - Code", "Code")
    system = FakeSystem(front, images or {1: editor(CODE)})
    model = FakeModel(answers)
    engine = AssistEngine(model, capturer(system), lambda: "English (UK)")
    pasted, player = [], FakePlayer()
    times = iter([0.0, held] + [held + 1.0] * 1000)  # press, release, then later calls
    assist = ScreenAssist(
        engine, FakeMic(audio), player,
        lambda: SimpleNamespace(screen_assist=SimpleNamespace(capture="window")),
        has_key=lambda: True, voice_name=lambda: "Kore", speak_allowed=lambda: speak,
        paste=lambda hwnd, text: pasted.append((hwnd, text)) or "Inserted.",
        to_wav=lambda pcm: b"WAV" + pcm[:4], has_speech=lambda pcm: speech,
        resample=lambda pcm, rate: pcm, mic_silence=mic_silence, clock=lambda: next(times))
    return SimpleNamespace(assist=assist, model=model, system=system, pasted=pasted,
                           player=player)


# ----- the service -------------------------------------------------------------------------------
def test_tap_the_hotkey_for_a_quick_look_that_is_read_aloud(qtbot):
    setup = make_assist(answers=["A Python file: a loop adds up prices. Line 12 never ends."])
    assist = setup.assist
    with qtbot.waitSignal(assist.answered, timeout=5000) as answered:
        assist.on_hotkey("screen_assist", "press")
        assist.on_hotkey("screen_assist", "release")
    exchange = answered.args[0]
    assert exchange.answer.startswith("A Python file") and not exchange.follow_up
    request = setup.model.calls[0]["turns"][0]
    assert not any(part.wav for part in request.parts)  # a tap: no spoken question
    qtbot.waitUntil(lambda: bool(setup.model.spoken), timeout=5000)
    assert setup.model.spoken[0].startswith("A Python file")
    qtbot.waitUntil(lambda: bool(setup.player.fed), timeout=5000)
    assert assist.mic.users == []


def test_hold_and_ask_sends_the_spoken_question(qtbot):
    setup = make_assist(audio=b"\x10\x00" * 16000, speech=True, speak=False, held=1.2)
    with qtbot.waitSignal(setup.assist.answered, timeout=5000):
        setup.assist.press()
        setup.assist.release()
    parts = setup.model.calls[0]["turns"][0].parts
    assert parts[-1].wav.startswith(b"WAV") and setup.model.spoken == []  # speaking off


def test_insert_pastes_only_after_a_click_and_never_sends(qtbot):
    setup = make_assist(answers=["Hi Sam, the figures will be with you by Friday."])
    with qtbot.waitSignal(setup.assist.answered, timeout=5000):
        setup.assist.ask(mode="reply", speak=False)
    assert setup.pasted == []
    assert setup.assist.insert("Hi Sam, the figures…") == "Inserted."
    assert setup.pasted == [(1, "Hi Sam, the figures…")]


def test_a_blocked_window_fails_politely(qtbot):
    setup = make_assist(front=Window(5, "Bitwarden", "Bitwarden"), images={})
    with qtbot.waitSignal(setup.assist.failed, timeout=5000) as failed:
        setup.assist.ask()
    assert failed.args[0] == REFUSAL and setup.model.calls == []


# ----- failures: logged with their traceback, shown with their message (D-054) -------------------
def logged_with_traceback(caplog, message: str):
    return [r for r in caplog.records
            if r.getMessage() == message and r.exc_info and r.exc_info[1] is not None]


def test_a_failed_request_is_logged_in_full_and_shown_with_its_message(qtbot, caplog):
    closed = RuntimeError("Cannot send a request, as the client has been closed.")
    setup = make_assist(answers=[closed])
    with qtbot.waitSignal(setup.assist.failed, timeout=5000) as failed:
        setup.assist.on_hotkey("screen_assist", "press")
        setup.assist.on_hotkey("screen_assist", "release")
    assert failed.args[0] == ("Unexpected error (RuntimeError): Cannot send a request, as the "
                              "client has been closed.")
    [record] = logged_with_traceback(caplog, "Screen Assist failed")
    assert record.exc_info[1] is closed and record.threadName == "screen-assist"


def test_a_capture_that_crashes_is_logged_on_its_thread(qtbot, caplog):
    setup = make_assist()

    def broken(region):
        raise OSError(6, "The handle is invalid")

    setup.assist.engine.capturer.system.grab = broken
    with qtbot.waitSignal(setup.assist.failed, timeout=5000) as failed:
        setup.assist.press()
        setup.assist.release()
    assert failed.args[0] == ("Wisp couldn't take the screenshot (OSError: [Errno 6] The handle "
                              "is invalid).")  # not "Couldn't reach Google"
    [record] = logged_with_traceback(caplog, "Screen capture failed")
    assert record.threadName == "assist-capture"
    assert setup.model.calls == []


def test_a_screenshot_that_never_arrives_is_a_capture_error(qtbot, monkeypatch):
    from concurrent.futures import Future

    from wisp.assist import service

    monkeypatch.setattr(service, "SHOT_TIMEOUT_S", 0.2)
    setup = make_assist()
    with qtbot.waitSignal(setup.assist.failed, timeout=5000) as failed:
        setup.assist.ask(shot_future=Future())  # never resolved
    assert failed.args[0] == "The screenshot took too long. Try again."  # not "network"
    assert setup.model.calls == []


def test_reading_aloud_failures_are_logged_in_full(qtbot, caplog):
    setup = make_assist(answers=["It's a terminal."])

    def broken(text, voice):
        raise ValueError("no audio in the response")

    setup.model.speak = broken
    setup.assist.speak("It's a terminal.")
    qtbot.waitUntil(lambda: not setup.assist.speaking, timeout=5000)
    [record] = logged_with_traceback(caplog, "Reading the answer aloud failed")
    assert record.threadName == "assist-speech"


def test_watch_mode_failures_are_logged_in_full(qtbot, caplog):
    from wisp.assist.engine import WatchCheck
    from wisp.assist.service import Watcher

    setup = make_assist()
    check = WatchCheck(setup.model, setup.assist.engine.capturer, lambda: 60.0)
    check.run = lambda: (_ for _ in ()).throw(RuntimeError("client closed"))
    settings = SimpleNamespace(screen_assist=SimpleNamespace(watch_auto_stop_min=5,
                                                             watch_interval_s=60))
    watcher = Watcher(check, lambda: settings, lambda: None, lambda: True)
    watcher.running = True
    watcher._tick()
    qtbot.waitUntil(lambda: watcher.last_status == "error", timeout=5000)
    [record] = logged_with_traceback(caplog, "Watch mode look failed")
    assert record.threadName == "watch"


# ----- a microphone that delivers only silence (D-055) --------------------------------------------
def test_holding_with_a_silent_mic_says_why_instead_of_a_quick_look(qtbot):
    setup = make_assist(audio=b"\x00\x00" * 16000,  # held 1 s, nothing but zeros
                        mic_silence=lambda pcm: "Wisp got only silence from the microphone.",
                        held=1.0)
    with qtbot.waitSignal(setup.assist.failed, timeout=5000) as failed:
        setup.assist.press()
        setup.assist.release()
    assert failed.args[0] == "Wisp got only silence from the microphone."
    assert setup.model.calls == [] and not setup.assist.busy
    # released while the mic was still opening: it is let go as soon as it opens
    qtbot.waitUntil(lambda: setup.assist.mic.users == [], timeout=3000)


def test_a_tap_with_a_silent_mic_still_takes_a_quick_look(qtbot):
    setup = make_assist(audio=b"\x00\x00" * 800,  # 50 ms: a tap
                        mic_silence=lambda pcm: "Wisp got only silence from the microphone.")
    with qtbot.waitSignal(setup.assist.answered, timeout=5000):
        setup.assist.press()
        setup.assist.release()
    assert len(setup.model.calls) == 1


# ----- every press ends in an answer, an error or "I didn't hear a question" (D-058) --------------
class SlowMic(FakeMic):
    """Takes ``delay`` seconds to open (PortAudio's first start took 1.6 s in the bug) and
    delivers ``audio`` only once open; ``fail`` makes it unavailable instead."""

    def __init__(self, audio=b"", delay=0.0, fail=""):
        super().__init__(audio)
        self.delay, self.fail = delay, fail
        self.callbacks = {}
        self.acquired_on = []

    def acquire(self, user):
        self.acquired_on.append(threading.current_thread().name)
        time.sleep(self.delay)
        if self.fail:
            from wisp.audio.capture import MicError

            raise MicError(self.fail)
        self.users.append(user)
        for callback in list(self.callbacks.values()):
            callback(self.audio)

    def subscribe(self, name, callback):
        self.callbacks[name] = callback

    def unsubscribe(self, name):
        self.callbacks.pop(name, None)


def outcomes(caplog) -> list[str]:
    return [r.getMessage().split("→ ")[-1] for r in caplog.records
            if r.getMessage().startswith("Screen Assist hotkey: held")]


def test_the_press_never_waits_for_the_microphone(qtbot, caplog):
    caplog.set_level("INFO", logger="wisp.assist.service")
    setup = make_assist(held=1.6)
    setup.assist.mic = SlowMic(delay=0.8)
    started = []
    setup.assist.started.connect(lambda: started.append(time.monotonic()))
    before = time.monotonic()
    setup.assist.press()
    assert time.monotonic() - before < 0.3 and started  # "Listening…" at once
    with qtbot.waitSignal(setup.assist.unheard, timeout=5000) as unheard:
        setup.assist.release()  # 5 ms after... the mic is still opening
    assert "still starting" in unheard.args[0] and unheard.args[0].startswith(
        "I didn't hear a question.")
    assert setup.assist.mic.acquired_on == ["assist-mic"]  # not the Qt thread
    assert setup.model.calls == []
    qtbot.waitUntil(lambda: setup.assist.mic.users == [], timeout=3000)  # let go once open
    assert outcomes(caplog) == ["no question (microphone still starting)"]


def test_holding_without_speaking_says_no_question_was_heard(qtbot, caplog):
    caplog.set_level("INFO", logger="wisp.assist.service")
    setup = make_assist(audio=b"\x20\x00" * 16000, held=1.0, speech=False)
    with qtbot.waitSignal(setup.assist.unheard, timeout=5000) as unheard:
        setup.assist.press()
        setup.assist.release()
    assert unheard.args[0] == ("I didn't hear a question. Hold the keys while you speak, or tap "
                               "them for a quick look.")
    assert setup.model.calls == [] and outcomes(caplog) == ["no question (no speech)"]


def test_no_microphone_a_hold_says_so_and_a_tap_still_looks(qtbot, caplog):
    caplog.set_level("INFO", logger="wisp.assist.service")
    setup = make_assist(held=1.0)
    setup.assist.mic = SlowMic(fail="Microphone is muted in Wisp.")
    with qtbot.waitSignal(setup.assist._mic_opened, timeout=3000):
        setup.assist.press()
    with qtbot.waitSignal(setup.assist.unheard, timeout=5000) as unheard:
        setup.assist.release()
    assert unheard.args[0] == "I didn't hear a question. Microphone is muted in Wisp."
    tap = make_assist(held=0.1, answers=["A spreadsheet."])
    tap.assist.mic = SlowMic(fail="Microphone is muted in Wisp.")
    with qtbot.waitSignal(tap.assist.answered, timeout=5000):
        tap.assist.press()
        tap.assist.release()
    assert outcomes(caplog) == ["no question (no microphone)", "quick look"]


def test_each_outcome_and_the_answer_are_logged(qtbot, caplog):
    caplog.set_level("INFO", logger="wisp.assist.service")
    setup = make_assist(audio=b"\x10\x00" * 16000, speech=True, speak=False, held=1.2,
                        answers=["It's a terminal."])
    with qtbot.waitSignal(setup.assist.answered, timeout=5000):
        setup.assist.press()
        setup.assist.release()
    text = caplog.text
    assert outcomes(caplog) == ["question"]
    assert "Screen Assist asks gemini-test (spoken question, from hotkey)" in text
    assert "Screen Assist answered in" in text


def test_a_press_while_a_question_runs_is_logged_not_lost(qtbot, caplog):
    caplog.set_level("INFO", logger="wisp.assist.service")
    setup = make_assist()
    setup.assist.busy = True
    setup.assist.press()
    setup.assist.release()
    assert "Screen Assist hotkey ignored: a question is still running" in caplog.text
    assert "release ignored (no press waiting)" in caplog.text


def test_google_busy_shows_on_the_card_while_wisp_retries(qtbot):
    from wisp.ui import theme
    from wisp.ui.island.assist_tab import AssistTab

    setup = make_assist()
    gate = threading.Event()

    def busy_answer(turns, system, json_schema=None, low_resolution=False, on_busy=None):
        on_busy("Google is busy, retrying… (2 of 3)")
        gate.wait(5)
        from wisp.assist.client import Reply

        return Reply("It's a code editor.", model="gemini-test")

    setup.model.answer = busy_answer
    watcher = SimpleNamespace(changed=setup.assist.speaking_changed, running=False, error="",
                              toggle=lambda: None, check=None, comments=0)
    tab = AssistTab(setup.assist, watcher, theme.palette("dark", "#7c5cff"))
    qtbot.addWidget(tab)
    notes = []
    setup.assist.progress.connect(notes.append)
    setup.assist.ask()
    qtbot.waitUntil(lambda: notes == ["Google is busy, retrying… (2 of 3)"], timeout=3000)
    assert tab.status.text() == "Google is busy, retrying… (2 of 3)"
    gate.set()
    qtbot.waitUntil(lambda: not setup.assist.busy, timeout=5000)


def test_unsubscribing_never_waits_for_a_stream_that_is_opening(monkeypatch):
    """The hotkey's release unsubscribes on the Qt thread while the mic may still be opening
    on "assist-mic"; that must not block (D-058). No real stream: opening is faked."""
    from wisp.audio import capture

    opening, done = threading.Event(), threading.Event()

    def slow_open(self):
        opening.set()
        time.sleep(0.6)
        self._stream = object()

    monkeypatch.setattr(capture.MicCapture, "_open_stream", slow_open)
    monkeypatch.setattr(capture.MicCapture, "_close_stream",
                        lambda self: setattr(self, "_stream", None))
    mic = capture.MicCapture(lambda: "")
    try:
        mic.subscribe("assist-1", lambda chunk: None)
        worker = threading.Thread(target=lambda: (mic.acquire("assist-1"), done.set()))
        worker.start()
        assert opening.wait(2)
        started = time.monotonic()
        mic.unsubscribe("assist-1")
        mic.preroll()
        assert time.monotonic() - started < 0.2 and not done.is_set()
        worker.join(3)
        mic.release("assist-1")
    finally:
        mic.close()


def test_the_mic_warm_up_starts_portaudio_without_opening_a_stream(monkeypatch, caplog):
    import sys

    from wisp.audio import capture

    class FakeSoundDevice:  # no RawInputStream: opening a stream would fail loudly
        default = SimpleNamespace(device=[3, 4])

        @staticmethod
        def query_devices(index):
            return {"name": "Microphone Array (Fake)"}

    monkeypatch.setitem(sys.modules, "sounddevice", FakeSoundDevice)
    monkeypatch.setattr(capture, "resolve", lambda name, kind: None)
    mic = capture.MicCapture.__new__(capture.MicCapture)
    mic._lock, mic._device_name = threading.RLock(), lambda: ""
    caplog.set_level("INFO", logger="wisp.audio.capture")
    mic.warm_up()
    assert "Audio ready in" in caplog.text and "no stream opened" in caplog.text


def test_screen_assist_failures_open_the_screen_tab():
    from wisp.ui.island.island import banner_style

    assert banner_style("Screen Assist failed") == ("warning", "warning", "Screen")
    assert banner_style("Problem") == ("warning", "warning", None)


def test_the_voice_tool_answers_from_a_worker_thread_without_tts(qtbot):
    from wisp.tools.builtin import screen as screen_tools

    setup = make_assist(answers=["It's a spreadsheet of Q3 sales."])
    ctx = ToolContext(Origin.VOICE, SimpleNamespace(assist=setup.assist))
    result = {}
    worker = threading.Thread(target=lambda: result.update(
        screen_tools.screen_assist(ctx, {"question": "what's this?", "mode": "explain"})))
    worker.start()
    qtbot.waitUntil(lambda: not worker.is_alive(), timeout=10000)
    assert result["answer"] == "It's a spreadsheet of Q3 sales."
    assert "untrusted" in result["note"] and setup.model.spoken == []
    blocked = make_assist(front=Window(5, "KeePass", "KeePass"), images={})
    bad = ToolContext(Origin.VOICE, SimpleNamespace(assist=blocked.assist))
    errors = []

    def run_blocked():
        try:
            screen_tools.screen_assist(bad, {})
        except ToolError as exc:
            errors.append(str(exc))

    worker = threading.Thread(target=run_blocked)
    worker.start()
    qtbot.waitUntil(lambda: not worker.is_alive(), timeout=10000)
    assert errors == [REFUSAL]


def test_watch_screen_tool_starts_and_stops():
    from wisp.tools.builtin import screen as screen_tools

    calls = []
    watcher = SimpleNamespace(start=lambda: calls.append("start") or True,
                              stop=lambda reason: calls.append(f"stop:{reason}"),
                              ends_at=__import__("time").time() + 1800, error="")
    ctx = ToolContext(Origin.VOICE, SimpleNamespace(watcher=watcher))
    assert screen_tools.watch_screen(ctx, {"on": True})["stops_in_minutes"] == 30
    assert screen_tools.watch_screen(ctx, {"on": False}) == {"watching": False}
    assert calls == ["start", "stop:asked"]


def test_look_at_screen_honours_the_blocklist(monkeypatch):
    from wisp.tools.builtin import screen as screen_tools

    vault = SimpleNamespace(hwnd=4, title="Vault - 1Password", process="1Password", pid=9,
                            minimized=False, foreground=True)
    monkeypatch.setattr(screen_tools.win, "input_desktop_available", lambda: True)
    monkeypatch.setattr(screen_tools.win, "list_windows", lambda: [vault])
    monkeypatch.setattr(screen_tools.win, "foreground_window", lambda: vault)
    ctx = ToolContext(Origin.VOICE, SimpleNamespace(live=object(), blocklist=Blocklist))
    with pytest.raises(ToolError, match=REFUSAL):
        screen_tools.look_at_screen(ctx, {"target": "window"})


# ----- the Screen tab ----------------------------------------------------------------------------
def shot_of(title="main.py - Code") -> Shot:
    from wisp.assist import imaging

    image = editor(CODE)
    small = imaging.downscale(image)
    return Shot(imaging.jpeg(small), small.size, imaging.fingerprint(small), 1, title, "window",
                masked=1)


def test_screen_tab_shows_what_was_sent_and_the_answer(qtbot):
    from PySide6.QtGui import QTextFormat

    from wisp.ui import theme
    from wisp.ui.island.assist_tab import AssistTab

    setup = make_assist()
    watcher = SimpleNamespace(changed=setup.assist.busy_changed, running=False, error="",
                              toggle=lambda: None, check=None, comments=0)
    tab = AssistTab(setup.assist, watcher, theme.palette("dark", "#7c5cff"))
    qtbot.addWidget(tab)
    assert "Hold Ctrl+Alt+Space" in tab.detail.text() and not tab.follow_up.isEnabled()
    answer = ("The loop never ends. Fix:\n\n```python\nwhile total < 10:\n    total += 1\n```\n\n"
              "See [the docs](https://example.com/run-this).")
    tab.show_exchange(Exchange("", answer, shot_of(), "review"))
    assert tab.thumb.pixmap().width() > 0 and "1 area hidden" in tab.detail.text()
    assert tab.title.text() == "The “main.py - Code” window"
    document = tab.view.document()
    block = document.begin()
    fences = []
    while block.isValid():
        if block.blockFormat().hasProperty(QTextFormat.Property.BlockCodeFence):
            fences.append(block.charFormat().fontFamilies())
        block = block.next()
    assert fences and fences[0][0] == theme.FONT_MONO[0]  # code in a monospace block
    assert not tab.view.openLinks() and not tab.view.openExternalLinks()
    assert tab.insert_button.isHidden()  # only for Reply
    tab.show_exchange(Exchange("Reply", "Hi Sam, …", shot_of(), "reply", follow_up=True))
    assert not tab.insert_button.isHidden() and len(tab.exchanges) == 2
    board = SimpleNamespace(text="", setText=lambda t: setattr(board, "text", t))
    tab.clipboard = board
    tab._copy()
    assert board.text == "Hi Sam, …"
    tab._insert()  # no conversation behind these hand-made answers: nowhere to paste
    assert setup.pasted == [] and tab.status.text() == "There's no window to insert into."


# ----- indicators --------------------------------------------------------------------------------
def test_watching_keeps_the_island_up_and_one_click_stops_it(island):  # noqa: F811
    from PySide6.QtCore import QPointF

    island.machine.set_autohide(True, 3000)
    island.machine.set_watching("Watching", 1.8e9 + 1800)
    assert not island.machine.hideable()
    island.machine.update()
    assert island.presentation.main.kind == "watching"
    stops = []
    island.watch_stop_requested.connect(lambda: stops.append(1))
    main = island._main
    island._click(QPointF(main.right() - 10, main.center().y()))
    assert stops == [1]
    island.machine.set_watching(None)
    assert island.machine.hideable() or island.machine.expanded


def test_tray_icon_badge_while_watching(qtbot):
    from PySide6.QtGui import QColor

    from wisp.ui.icons import orb_pixmap

    plain = orb_pixmap(32, "#7c5cff").toImage()
    badged = orb_pixmap(32, "#7c5cff", badge="#f5a524").toImage()
    corner = QColor(badged.pixel(27, 27))
    assert corner.red() > 200 and corner.green() > 120 and plain.pixel(27, 27) != \
        badged.pixel(27, 27)


def test_circle_to_ask_paints_over_blocked_windows(qtbot):
    from PySide6.QtGui import QColor, QPixmap

    from wisp.circle import mask_shot

    shot = QPixmap(400, 300)
    shot.fill(QColor("white"))
    masked = mask_shot(shot, (0, 0, 400, 300), [(200, 0, 400, 300)])
    image = masked.toImage()
    assert QColor(image.pixel(300, 150)).red() < 60 and QColor(image.pixel(50, 150)).red() == 255
    assert mask_shot(shot, None, [(0, 0, 10, 10)]) is None  # unmatched screen: refuse
    assert mask_shot(shot, None, []) is shot


# ----- settings ----------------------------------------------------------------------------------
def test_screen_assist_settings_and_the_island_hotkey_move():
    settings = Settings()
    assert settings.hotkeys.screen_assist == "ctrl+alt+space"
    assert settings.hotkeys.island == "ctrl+alt+i" and validate(settings) == []
    old = Settings.from_dict({"hotkeys": {"island": "Ctrl+Alt+Space", "dictation": "ctrl+win"}})
    assert old.hotkeys.island == "ctrl+alt+i" and old.hotkeys.screen_assist == "ctrl+alt+space"
    custom = Settings.from_dict({"hotkeys": {"island": "ctrl+shift+i"}})
    assert custom.hotkeys.island == "ctrl+shift+i"
    clash = Settings()
    clash.hotkeys.watch = "ctrl+alt+space"
    assert any("Watch mode" in p or "Screen Assist" in p for p in validate(clash))
    bad = Settings()
    bad.screen_assist.watch_interval_s = 5
    bad.screen_assist.capture = "everything"
    problems = validate(bad)
    assert any("10–600" in p for p in problems) and any("'window'" in p for p in problems)
    assert "1Password" in settings.screen_assist.blocked_apps
    assert "Incognito" in settings.screen_assist.blocked_titles


def test_settings_page_round_trips_the_blocklist(qtbot):
    from wisp.ui.settings.assist_page import AssistPage

    page = AssistPage()
    qtbot.addWidget(page)
    settings = Settings()
    page.load(settings)
    page.apps.setPlainText("Slack\nslack\n  \nSignal")
    page.titles.setPlainText("Payroll")
    page.interval.setValue(45)
    page.apply(settings)
    assert settings.screen_assist.blocked_apps == ["Slack", "Signal"]
    assert settings.screen_assist.blocked_titles == ["Payroll"]
    assert settings.screen_assist.watch_interval_s == 45
    page._defaults()
    assert "Bitwarden" in page.apps.toPlainText()


def test_blocked_exception_is_the_refusal():
    assert str(Blocked(REFUSAL)) == "I don't look at that window."
