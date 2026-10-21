"""D-055: a microphone that delivers only silence (privacy switch, mute key, wrong input) is
told apart from a quiet room, and the notice names the Windows setting to check; the
"Mic levels" log line uses plain numbers. Fake audio and a fake registry only: nothing here
opens the microphone or reads this PC's settings."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from wisp.audio import mic_check
from wisp.audio.convert import MicConverter

RATE = 16000


def pcm(seconds: float, amplitude: float, seed: int = 0) -> bytes:
    """16 kHz int16 noise of about ``amplitude`` int16 steps RMS (0 = digital silence)."""
    rng = np.random.default_rng(seed)
    samples = rng.normal(0, amplitude, int(RATE * seconds)) if amplitude else \
        np.zeros(int(RATE * seconds))
    return np.clip(np.round(samples), -32768, 32767).astype("<i2").tobytes()


def lsb_noise(seconds: float) -> bytes:
    """What the frozen build logged: about −96 dBFS, samples of 0 and ±1."""
    rng = np.random.default_rng(1)
    return rng.choice([-1, 0, 0, 0, 1], int(RATE * seconds)).astype("<i2").tobytes()


def registry(values: dict[str, str | None]):
    """A fake reader for (hive, subkey) → "Allow"/"Deny"/None, keyed by the switch's name."""
    names = {(hive, subkey): name for hive, subkey, name in mic_check.SWITCHES}

    def read(hive: str, subkey: str) -> str | None:
        return values.get(names[(hive, subkey)])
    return read


ALL_ALLOWED = {"Microphone access": "Allow", "Let apps access your microphone": "Allow",
               "Let desktop apps access your microphone": "Allow"}


# ----- silence --------------------------------------------------------------------------------
def test_digital_silence_and_lsb_noise_are_dead_but_a_quiet_room_is_not():
    assert mic_check.is_dead_silence(pcm(1.0, 0))
    assert mic_check.is_dead_silence(lsb_noise(1.0))  # the −96 dBFS of the bug report
    assert not mic_check.is_dead_silence(pcm(1.0, 33))  # a quiet room, about −60 dBFS
    assert not mic_check.is_dead_silence(pcm(1.0, 8))  # a very quiet mic, about −72 dBFS


def test_too_little_audio_is_not_judged():
    assert not mic_check.is_dead_silence(pcm(0.1, 0))  # a tap: the default question applies
    assert not mic_check.is_dead_silence(b"")


def test_every_channel_must_be_silent():
    assert mic_check.channels_silent([-96.4, -96.5, -96.5, -96.5])
    assert not mic_check.channels_silent([-96.4, -48.0, -96.5, -96.5])
    assert not mic_check.channels_silent([])


# ----- privacy switches and the notice ---------------------------------------------------------
def test_privacy_states_are_read_in_settings_order():
    states = mic_check.privacy_states(registry({**ALL_ALLOWED,
                                                "Let desktop apps access your microphone":
                                                "Deny"}))
    assert [name for name, _value in states] == ["Microphone access",
                                                 "Let apps access your microphone",
                                                 "Let desktop apps access your microphone"]
    assert mic_check.blocked_switches(states) == ["Let desktop apps access your microphone"]


def test_a_failing_read_counts_as_unknown_not_blocked():
    def broken(hive, subkey):
        raise PermissionError("denied")

    states = mic_check.privacy_states(broken)
    assert all(value is None for _name, value in states)
    assert mic_check.blocked_switches(states) == []


def test_the_notice_names_the_switch_that_is_off():
    states = mic_check.privacy_states(registry({**ALL_ALLOWED,
                                                "Let desktop apps access your microphone":
                                                "Deny"}))
    notice = mic_check.silence_notice("Microphone Array (AMD Audio Device)", states)
    assert "Windows is blocking it" in notice
    assert "Turn on “Let desktop apps access your microphone”" in notice
    assert "Privacy & security → Microphone" in notice
    assert "Microphone Array (AMD Audio Device)" in notice


def test_with_every_switch_on_the_notice_lists_what_to_check():
    notice = mic_check.silence_notice("Microphone Array (AMD Audio Device)",
                                      mic_check.privacy_states(registry(ALL_ALLOWED)))
    assert "nothing was sent" in notice
    for hint in ("Let desktop apps access your microphone", "mute key",
                 "System → Sound → Input", "Test microphone"):
        assert hint in notice


def test_notice_if_silent_logs_the_switches(caplog):
    caplog.set_level(logging.WARNING, logger="wisp.audio.mic_check")
    states = lambda: mic_check.privacy_states(registry(ALL_ALLOWED))  # noqa: E731
    assert mic_check.notice_if_silent(pcm(1.0, 33), "Mic", states) is None
    notice = mic_check.notice_if_silent(lsb_noise(1.0), "Mic", states)
    assert notice and "“Mic”" in notice
    assert "Microphone access=Allow" in caplog.text and "delivered only silence" in caplog.text


# ----- the "Mic levels" log line ------------------------------------------------------------------
def test_channel_levels_are_plain_numbers():
    converter = MicConverter(44100, 4, "float32")
    frames = np.full((4410, 4), 1.5e-5, dtype=np.float32)
    converter.process(frames.tobytes())
    levels = converter.channel_levels()
    assert all(type(level) is float for level in levels)
    assert "np.float64" not in repr(levels)


def test_the_levels_line_has_plain_numbers_and_warns_when_silent(caplog, monkeypatch):
    from wisp.audio.capture import MicCapture

    real = mic_check.privacy_states
    monkeypatch.setattr(mic_check, "privacy_states",
                        lambda read=None: real(registry(ALL_ALLOWED)))
    capture = MicCapture.__new__(MicCapture)  # no stream, no delivery thread
    capture.device_label = "Microphone Array (AMD Audio Device)"
    converter = MicConverter(44100, 4, "float32")
    for _ in range(60):  # 32 ms chunks for ~2 s: the smoothed power settles
        converter.process(np.full((1411, 4), 1.5e-5, dtype=np.float32).tobytes())
    caplog.set_level(logging.INFO, logger="wisp.audio.capture")
    capture._log_levels(converter, np.zeros(16000, dtype=np.int16))
    line = next(r.getMessage() for r in caplog.records if "Mic levels" in r.getMessage())
    assert "np.float64" not in line
    assert "channels (dBFS) -96.5, -96.5, -96.5, -96.5; mixing 1, 2, 3, 4" in line
    warning = next(r for r in caplog.records if r.levelno == logging.WARNING)
    assert "Microphone Array (AMD Audio Device)" in warning.getMessage()
    assert "Let desktop apps access your microphone=Allow" in warning.getMessage()


def test_a_working_mic_logs_no_warning(caplog):
    from wisp.audio.capture import MicCapture

    capture = MicCapture.__new__(MicCapture)
    capture.device_label = "Mic"
    converter = MicConverter(48000, 2, "float32")
    rng = np.random.default_rng(0)
    converter.process(rng.normal(0, 0.01, (4800, 2)).astype(np.float32).tobytes())
    caplog.set_level(logging.INFO, logger="wisp.audio.capture")
    capture._log_levels(converter, np.zeros(16000, dtype=np.int16))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ----- voice and dictation ------------------------------------------------------------------------
@pytest.mark.qt
def test_a_dead_mic_in_push_to_talk_shows_the_mic_notice(qtbot):
    from wisp.audio.playback import Player
    from wisp.voice import DROPPED_MESSAGES, VoiceSignals, make_callbacks

    signals = VoiceSignals()
    messages = []
    signals.hint.connect(messages.append)
    callbacks = make_callbacks(signals, Player.__new__(Player), lambda text: None,
                               mic_notice=lambda: "Turn on the desktop apps switch.")
    callbacks.turn_dropped("mic_silent")
    callbacks.turn_dropped("silent")
    qtbot.waitUntil(lambda: len(messages) == 2, timeout=3000)
    assert messages == ["Turn on the desktop apps switch.", DROPPED_MESSAGES["silent"]]


@pytest.mark.qt
def test_dictation_with_a_dead_mic_says_which_setting_to_check(qtbot):
    from tests.test_dictation import Recorder, make, names

    rec = Recorder()
    controller, mic, hud, stats = make(rec)
    controller.deps.mic_silence = lambda audio: (
        "Wisp got only silence from the microphone." if mic_check.is_dead_silence(audio)
        else None)
    controller.start()
    mic.subs["dictation"](b"\x00\x00" * 32000)  # 2 s of digital silence
    controller.stop()
    assert "Wisp got only silence from the microphone." in hud.messages
    assert "transcribe" not in names(rec) and stats.events == []


# ----- Wisp.exe --mic-check (MT-116) ------------------------------------------------------------
class ReportMic:
    """A fake MicCapture: delivers ``pcm`` once opened, with fixed channel levels."""

    def __init__(self, pcm=b"", levels=(-40.0, -41.5), fail=""):
        self.pcm, self.levels, self.fail = pcm, list(levels), fail
        self.subscribers, self.events = {}, []
        self.device_label, self.format_description = "Microphone Array (Fake)", "44100 Hz × 2 ch"

    def subscribe(self, name, callback):
        self.subscribers[name] = callback

    def unsubscribe(self, name):
        self.subscribers.pop(name)

    def acquire(self, user):
        if self.fail:
            from wisp.audio.capture import MicError

            raise MicError(self.fail)
        self.events.append("open")
        for callback in self.subscribers.values():
            callback(self.pcm)

    def channel_levels(self):
        return self.levels

    def release(self, user):
        self.events.append("released")

    def close(self):
        self.events.append("closed")


def states_allowed():
    return mic_check.privacy_states(registry(ALL_ALLOWED))


def test_mic_check_reports_a_working_microphone():
    from wisp.audio import mic_report

    mic = ReportMic(pcm(1.5, 33))
    result = mic_report.measure(lambda: mic, seconds=0, states=states_allowed)
    assert result["opened"] and not result["digital_silence"] and result["seconds"] == 1.5
    assert result["channels_dbfs"] == [-40.0, -41.5] and -65 < result["output_dbfs"] < -55
    assert result["privacy"]["Let desktop apps access your microphone"] == "Allow"
    assert result["verdict"].startswith("Sound arrived") and mic.events == [
        "open", "released", "closed"]
    assert "program" in result and result["frozen"] is False


def test_mic_check_tells_silence_from_a_blocked_switch():
    from wisp.audio import mic_report

    silent = mic_report.measure(lambda: ReportMic(lsb_noise(1.5), levels=(-96.4, -96.5)),
                                seconds=0, states=states_allowed)
    assert silent["digital_silence"] and silent["silent_channels"]
    assert "Compare with the other build" in silent["verdict"]
    blocked = mic_report.measure(
        lambda: ReportMic(pcm(1.5, 0), levels=(-120.0,)), seconds=0,
        states=lambda: mic_check.privacy_states(registry(
            {**ALL_ALLOWED, "Let desktop apps access your microphone": "Deny"})))
    assert blocked["verdict"] == ("Windows is blocking it: Let desktop apps access your "
                                  "microphone is off.")


def test_mic_check_reports_a_microphone_that_does_not_open():
    from wisp.audio import mic_report

    mic = ReportMic(fail="Microphone unavailable.")
    result = mic_report.measure(lambda: mic, seconds=0, states=states_allowed)
    assert result["opened"] is False and result["error"] == "Microphone unavailable."
    assert result["verdict"] == "The microphone didn't open: Microphone unavailable."
    assert mic.events == ["closed"]


def test_mic_check_exit_code_fails_on_silent_channels(monkeypatch, tmp_path):
    """A start-up click lifts the peak above digital silence; silent channels still fail."""
    import json

    from wisp.audio import mic_report

    real_measure = mic_report.measure
    click = bytearray(lsb_noise(1.5))
    click[100:102] = (900).to_bytes(2, "little", signed=True)
    for data, levels, expected in ((bytes(click), (-93.0, -93.1), 1),
                                   (pcm(1.5, 33), (-40.0, -41.0), 0)):
        def fake_measure(data=data, levels=levels):
            return real_measure(lambda: ReportMic(data, levels=levels), seconds=0,
                                states=states_allowed)

        monkeypatch.setattr(mic_report, "measure", fake_measure)
        report = tmp_path / "mic.json"
        assert mic_report.run(report) == expected
        assert json.loads(report.read_text(encoding="utf-8"))["opened"] is True
