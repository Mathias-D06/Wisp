from __future__ import annotations

from types import SimpleNamespace

import pytest

from wisp.audio.capture import MicError
from wisp.live.session import LiveState
from wisp.settings import SettingsStore
from wisp.tools.confirm import ConfirmationManager

pytestmark = pytest.mark.qt


class FakeLive:
    def __init__(self, key=True):
        self.key = key
        self.calls: list[tuple] = []
        self.state = LiveState.IDLE

    def has_key(self):
        return self.key

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, *args))
        return record


class FakeMic:
    def __init__(self, fail=False):
        self.fail = fail
        self.users: set[str] = set()
        self.subs: dict = {}
        self.muted = False
        self.level = 0.3

    def acquire(self, user):
        if self.fail:
            raise MicError("Microphone unavailable.")
        self.users.add(user)

    def release(self, user):
        self.users.discard(user)

    def subscribe(self, name, cb):
        self.subs[name] = cb

    def unsubscribe(self, name):
        self.subs.pop(name, None)

    def set_muted(self, muted):
        self.muted = muted

    def preroll(self, ms=None):
        return b"pre" if ms else b""


class FakePlayer:
    level = 0.0

    def __init__(self):
        self.playing = False
        self.cleared = 0

    def clear(self):
        self.cleared += 1

    def is_playing(self):
        return self.playing


def make(tmp_path, key=True, mic_fail=False):
    from wisp.voice import VoiceController, VoiceSignals

    live, mic, player = FakeLive(key), FakeMic(mic_fail), FakePlayer()
    confirmations = ConfirmationManager()
    voice = VoiceController(live, mic, player, VoiceSignals(), SettingsStore(tmp_path / "s.json"),
                            confirmations, lambda t, m: None)
    messages: list[str] = []
    voice.message.connect(messages.append)
    return voice, live, mic, player, confirmations, messages


def names(live):
    return [c[0] for c in live.calls]


def test_push_to_talk_round_trip(qtbot, tmp_path):
    voice, live, mic, player, _, _ = make(tmp_path)
    voice.on_hotkey("push_to_talk", "press")
    assert names(live) == ["begin_turn", "push_audio"]  # pre-roll from the arming time
    assert "voice" in mic.users and "voice" in mic.subs
    assert player.cleared == 1  # barge-in
    assert voice.compute_visual()[0] == "listening"
    voice.on_hotkey("push_to_talk", "release")
    assert names(live)[-1] == "end_turn" and not mic.users
    assert voice.compute_visual()[0] == "thinking"
    player.playing = True
    voice._on_model_text("Hi", False)
    assert voice.compute_visual()[0] == "speaking"


def test_orb_click_toggles(qtbot, tmp_path):
    voice, live, *_ = make(tmp_path)
    voice.toggle_talk()
    voice.toggle_talk()  # a double-click: the second click is ignored
    assert names(live) == ["begin_turn"]
    voice._orb_at -= 1.0  # a separate click later
    voice.toggle_talk()
    assert names(live) == ["begin_turn", "end_turn"]


def test_talk_button_click_or_hold(qtbot, tmp_path, monkeypatch):
    from wisp import voice as voice_module

    clock = {"t": 100.0}
    monkeypatch.setattr(voice_module.time, "monotonic", lambda: clock["t"])
    voice, live, _mic, _, _, messages = make(tmp_path)
    voice.talk_pressed()  # click: press and release quickly → keeps listening
    clock["t"] += 0.1
    voice.talk_released()
    assert names(live) == ["begin_turn"] and voice.talking
    assert "click Talk again" in messages[-1]
    clock["t"] += 3
    voice.talk_pressed()  # second click sends
    voice.talk_released()
    assert names(live) == ["begin_turn", "end_turn"] and not voice.talking
    voice.talk_pressed()  # hold: press, speak, release → sends on release
    clock["t"] += 2
    voice.talk_released()
    assert names(live) == ["begin_turn", "end_turn", "begin_turn", "end_turn"]


def test_push_to_talk_hotkey_opens_mic_on_arm_and_sends_preroll(qtbot, tmp_path):
    voice, live, mic, *_ = make(tmp_path)
    voice.on_hotkey("push_to_talk", "arm")
    assert "ptt-arm" in mic.users and names(live) == []
    voice.on_hotkey("push_to_talk", "disarm")  # e.g. Win+Alt+R: nothing sent, mic closed
    assert not mic.users and names(live) == []
    voice.on_hotkey("push_to_talk", "arm")
    voice.on_hotkey("push_to_talk", "press")
    assert names(live) == ["begin_turn", "push_audio"] and live.calls[1][1] == b"pre"
    assert mic.users == {"voice"}
    voice.on_hotkey("push_to_talk", "release")
    assert names(live)[-1] == "end_turn" and not mic.users


def test_cancel_drops_turn(qtbot, tmp_path):
    voice, live, mic, *_ = make(tmp_path)
    voice.on_hotkey("push_to_talk", "press")
    voice.on_hotkey("push_to_talk", "cancel")
    assert names(live) == ["begin_turn", "push_audio", "cancel_turn"] and not mic.users


def test_no_key_prompts_to_add_key(qtbot, tmp_path):
    voice, live, _mic, _, _, messages = make(tmp_path, key=False)
    voice.ptt_press()
    voice.send_text("hello")
    assert "begin_turn" not in names(live) and "send_text" not in names(live)
    assert messages and all("API key" in m for m in messages)
    voice._on_state(LiveState.NO_KEY.value, "Add your Gemini API key")
    assert voice.compute_visual() == ("offline", 0.0, "Add your API key")


def test_mic_error_is_reported(qtbot, tmp_path):
    voice, live, _, _, _, messages = make(tmp_path, mic_fail=True)
    voice.ptt_press()
    assert messages == ["Microphone unavailable."]
    assert names(live) == []


def test_typed_text_counts_as_user_evidence(qtbot, tmp_path):
    from wisp.tools.base import Origin

    voice, live, _, _, confirmations, _ = make(tmp_path)
    item = confirmations.create("delete_file", {}, "delete", Origin.VOICE)
    voice.send_text("yes")
    assert item.state == "approved"
    assert ("send_text", "yes") in live.calls


def test_mute_persists_and_cancels_turn(qtbot, tmp_path):
    voice, live, mic, *_ = make(tmp_path)
    voice.ptt_press()
    voice.set_muted(True)
    assert mic.muted and "cancel_turn" in names(live)
    assert voice.settings_store.get().audio.mic_muted is True
    assert voice.compute_visual()[2] == "Mic muted"


def test_offline_state_visual(qtbot, tmp_path):
    voice, *_ = make(tmp_path)
    voice._on_state(LiveState.OFFLINE.value, "Can't reach Google. Retrying in 4 s…")
    state, _, text = voice.compute_visual()
    assert state == "offline" and "Retrying" in text


def test_always_listening_follows_settings_from_any_source(qtbot, tmp_path):
    voice, live, mic, *_ = make(tmp_path)
    voice.set_always_listening(True)  # console / tray path
    assert voice.always_listening and "always" in mic.users and "always" in mic.subs
    assert ("request_reconnect",) in live.calls and ("connect",) in live.calls
    voice.settings_store.update(lambda s: setattr(s.audio, "always_listening", False))  # Settings
    assert not voice.always_listening and "always" not in mic.users
    calls = len(live.calls)
    voice.settings_store.update(lambda s: setattr(s.general, "typing_wpm", 50))  # unrelated
    assert len(live.calls) == calls


def test_too_short_turn_shows_a_hint(qtbot, tmp_path):
    from wisp.voice import DROPPED_MESSAGES, VoiceController, VoiceSignals, make_callbacks

    signals = VoiceSignals()
    voice = VoiceController(FakeLive(), FakeMic(), FakePlayer(), signals,
                            SettingsStore(tmp_path / "s.json"), ConfirmationManager(),
                            lambda t, m: None)
    messages: list[str] = []
    voice.message.connect(messages.append)
    player = SimpleNamespace(feed=lambda pcm: None, clear=lambda: None)
    callbacks = make_callbacks(signals, player, lambda text: None)
    callbacks.turn_dropped("short")
    callbacks.turn_dropped("silent")
    qtbot.waitUntil(lambda: messages == [DROPPED_MESSAGES["short"], DROPPED_MESSAGES["silent"]],
                    timeout=1000)
    assert "Test microphone" in DROPPED_MESSAGES["silent"]


def test_visual_is_emitted_only_on_change(qtbot, tmp_path):
    """An idle Wisp emits nothing, so nothing repaints (D-044)."""
    voice, _live, mic, *_ = make(tmp_path)
    seen = []
    voice.visual.connect(lambda state, level, text: seen.append((state, round(level, 2), text)))
    for _ in range(5):
        voice._refresh_visual()
    assert len(seen) <= 1
    voice.on_hotkey("push_to_talk", "press")
    voice._refresh_visual()
    mic.level = 0.31  # unchanged within 0.02 → no emission
    voice._refresh_visual()
    mic.level = 0.6
    voice._refresh_visual()
    assert [s[0] for s in seen[-2:]] == ["listening", "listening"] and seen[-1][1] == 0.6
