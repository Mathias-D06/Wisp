from __future__ import annotations

import io
import os
import wave
from types import SimpleNamespace

import pytest

from wisp.ai.dictation import clean_output, pcm_to_wav, system_prompt, word_count


# ----- clean-up helpers -------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("Meet at 10.", "Meet at 10."),
    ('"Meet at 10."', "Meet at 10."),
    ("Transcription: hello there", "hello there"),
    ("```\nhello\n```", "hello"),
    ("(no speech)", ""),
    ("", ""),
    (None, ""),
    ("“Quoted”", "Quoted"),
])
def test_clean_output(raw, expected):
    assert clean_output(raw) == expected


def test_wav_header():
    data = pcm_to_wav(b"\x00\x00" * 16000)
    with wave.open(io.BytesIO(data)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        assert wav.getnframes() == 16000


def test_prompt_mentions_self_corrections():
    prompt = system_prompt("English")
    assert "meet at nine... no, ten" in prompt and "meet at 10" in prompt
    assert "normally speaks English" in prompt and "spelling conventions" in prompt
    assert word_count("Meet at 10, okay?") == 4


SPEECH = (3000).to_bytes(2, "little", signed=True)  # -21 dBFS


# ----- controller ---------------------------------------------------------------------------
class FakeMic:
    level = 0.2

    def __init__(self):
        self.subs = {}
        self.users = set()

    def acquire(self, user):
        self.users.add(user)

    def release(self, user):
        self.users.discard(user)

    def subscribe(self, name, cb):
        self.subs[name] = cb

    def unsubscribe(self, name):
        self.subs.pop(name, None)

    def feed(self, seconds):
        self.subs["dictation"](SPEECH * int(16000 * seconds))


class FakeHud:
    def __init__(self):
        self.messages = []

    def show_state(self, text, dot=None, level=None):
        self.messages.append(text)

    def flash(self, text, ms=0, dot=None):
        self.messages.append(text)

    def hide_now(self):
        self.messages.append("<hidden>")


class Recorder:
    def __init__(self, transcript="Meet at 10.", elevated=False, key=True):
        self.calls = []
        self.seq = 1
        self.held = 0
        self.transcript = transcript
        self.elevated = elevated
        self.key = key
        self.window = SimpleNamespace(hwnd=111, pid=5, title="Notepad")

    def deps(self):
        from wisp.dictation import DictationDeps

        def set_text(text):
            self.seq += 1
            self.calls.append(("set_text", text))

        def modifiers_down():
            self.held = max(0, self.held - 1)
            return self.held > 0

        return DictationDeps(
            transcribe=lambda pcm, on_busy=None: (self.calls.append(("transcribe", len(pcm)))
                                                  or self.transcript),
            has_key=lambda: self.key,
            snapshot=lambda: self.calls.append(("snapshot",)) or "SAVED",
            set_text=set_text,
            restore=lambda snap: self.calls.append(("restore", snap)),
            clipboard_sequence=lambda: self.seq,
            paste=lambda: self.calls.append(("paste",)),
            modifiers_down=modifiers_down,
            foreground=lambda: self.window,
            activate=lambda hwnd: self.calls.append(("activate", hwnd)) or True,
            target_is_elevated=lambda w: self.elevated,
        )


class FakeStats:
    def __init__(self):
        self.events = []

    def record(self, kind, words=0, seconds=0.0):
        self.events.append((kind, words, round(seconds, 1)))


def make(rec):
    from wisp.dictation import DictationController

    mic, hud, stats = FakeMic(), FakeHud(), FakeStats()
    controller = DictationController(rec.deps(), mic, hud, stats, lambda t, m: None)
    return controller, mic, hud, stats


def names(rec):
    return [c[0] for c in rec.calls]


@pytest.mark.qt
def test_full_flow_pastes_and_restores(qtbot):
    rec = Recorder()
    controller, mic, _hud, stats = make(rec)
    controller.on_hotkey("dictation", "press")
    assert "dictation" in mic.users
    mic.feed(1.5)
    controller.on_hotkey("dictation", "release")
    qtbot.waitUntil(lambda: "paste" in names(rec), timeout=3000)
    assert names(rec)[:4] == ["transcribe", "snapshot", "set_text", "paste"]
    assert rec.calls[2] == ("set_text", "Meet at 10.")
    qtbot.waitUntil(lambda: "restore" in names(rec), timeout=2000)
    assert ("restore", "SAVED") in rec.calls
    assert stats.events == [("dictation", 3, 1.5)]
    assert not mic.users


@pytest.mark.qt
def test_waits_for_modifiers_before_paste(qtbot):
    rec = Recorder()
    rec.held = 5  # keys still down for a few polls
    controller, mic, *_ = make(rec)
    controller.start()
    mic.feed(1.0)
    controller.stop()
    qtbot.waitUntil(lambda: "paste" in names(rec), timeout=3000)
    assert rec.held == 0


@pytest.mark.qt
def test_no_restore_if_clipboard_changed(qtbot):
    rec = Recorder()
    controller, mic, *_ = make(rec)
    controller.start()
    mic.feed(1.0)
    controller.stop()
    qtbot.waitUntil(lambda: "paste" in names(rec), timeout=3000)
    rec.seq += 5  # the user copied something else right away
    qtbot.wait(800)
    assert "restore" not in names(rec)


@pytest.mark.qt
def test_short_press_and_cancel_do_nothing(qtbot):
    rec = Recorder()
    controller, mic, _hud, _ = make(rec)
    controller.start()
    mic.feed(0.1)
    controller.stop()
    controller.start()
    mic.feed(2.0)
    controller.on_hotkey("dictation", "cancel")
    qtbot.wait(100)
    assert rec.calls == []


@pytest.mark.qt
def test_elevated_target_copies_instead(qtbot):
    rec = Recorder(elevated=True)
    controller, mic, hud, _stats = make(rec)
    controller.start()
    mic.feed(1.0)
    controller.stop()
    qtbot.waitUntil(lambda: "set_text" in names(rec), timeout=3000)
    assert "paste" not in names(rec)
    assert any("admin" in m for m in hud.messages)


@pytest.mark.qt
def test_no_key_prompts(qtbot):
    rec = Recorder(key=False)
    controller, mic, hud, _ = make(rec)
    controller.start()
    assert not mic.users and any("API key" in m for m in hud.messages)


@pytest.mark.qt
def test_empty_transcript(qtbot):
    rec = Recorder(transcript="")
    controller, mic, hud, stats = make(rec)
    controller.start()
    mic.feed(1.0)
    controller.stop()
    qtbot.waitUntil(lambda: "No speech heard" in hud.messages, timeout=3000)
    assert "set_text" not in names(rec) and stats.events == []



def test_silent_dictation_is_never_sent(qtbot):
    """Silence makes the model invent text; it must never be pasted (D-039)."""
    from wisp.dictation import SILENT_MESSAGE

    rec = Recorder()
    controller, mic, hud, stats = make(rec)
    controller.start()
    mic.subs["dictation"](b"\x00\x00" * 32000)  # 2 s of silence
    controller.stop()
    assert SILENT_MESSAGE in hud.messages
    assert "transcribe" not in names(rec) and stats.events == []


# ----- real clipboard and paste (opt-in: they touch your clipboard / send Ctrl+V) -----------
@pytest.mark.windows
@pytest.mark.qt
@pytest.mark.skipif(os.environ.get("WISP_CLIPBOARD_TEST") != "1", reason="opt-in")
def test_real_clipboard_round_trip(qtbot):
    import win32clipboard as wcb
    from PySide6.QtWidgets import QWidget

    from wisp.system import clipboard

    owner = QWidget()
    hwnd = int(owner.winId())
    users_clipboard = clipboard.snapshot(hwnd)
    try:
        custom = wcb.RegisterClipboardFormat("WispPytestFormat")
        with clipboard.opened(hwnd):
            wcb.EmptyClipboard()
            wcb.SetClipboardData(wcb.CF_UNICODETEXT, "original text ✓")
            wcb.SetClipboardData(custom, b"\x01\x02\x03binary")
        saved = clipboard.snapshot(hwnd)
        clipboard.set_text("dictated words", hwnd)
        with clipboard.opened(hwnd):
            assert clipboard.exclusion_requested()
        assert clipboard.get_text(hwnd) == "dictated words"
        assert clipboard.read_for_history(hwnd).excluded
        clipboard.restore(saved, hwnd, exclude_from_history=False)
        assert clipboard.get_text(hwnd) == "original text ✓"
        with clipboard.opened(hwnd):
            assert wcb.GetClipboardData(custom).startswith(b"\x01\x02\x03binary")
            assert not clipboard.exclusion_requested()
    finally:
        clipboard.restore(users_clipboard, hwnd, exclude_from_history=False)


@pytest.mark.windows
@pytest.mark.qt
@pytest.mark.skipif(os.environ.get("WISP_INPUT_TEST") != "1", reason="opt-in: sends Ctrl+V")
def test_real_paste_into_focused_field(qtbot):
    from PySide6.QtWidgets import QLineEdit, QWidget

    from wisp.system import clipboard
    from wisp.winapi import input as winput
    from wisp.winapi import windows as win

    owner = QWidget()
    hwnd_owner = int(owner.winId())
    users_clipboard = clipboard.snapshot(hwnd_owner)
    field = QLineEdit()
    field.setWindowTitle("Wisp paste probe")
    field.show()
    qtbot.waitExposed(field)
    win.activate(int(field.winId()))
    field.activateWindow()
    field.setFocus()
    qtbot.wait(200)
    if win.foreground_window() is None or win.foreground_window().hwnd != int(field.winId()):
        pytest.skip("Windows did not let the test window take focus")
    try:
        clipboard.set_text("meet at 10", hwnd_owner)
        winput.paste_shortcut()
        qtbot.waitUntil(lambda: field.text() == "meet at 10", timeout=3000)
    finally:
        clipboard.restore(users_clipboard, hwnd_owner, exclude_from_history=False)
