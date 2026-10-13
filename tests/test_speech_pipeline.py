"""D-039/D-040: the audio Wisp sends (debug WAV), the language lock, capture through a fake
sound device, and the microphone test report."""

from __future__ import annotations

import asyncio
import time
import wave
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

from tests.fakes import SPEECH_CHUNK, FakeLiveServer, speak, until
from wisp.audio.debug_wav import DebugAudioRecorder, debug_dir, prune, save_pcm
from wisp.live.config import build_live_config, language_rule, system_instruction
from wisp.live.session import LiveCallbacks, LiveSessionManager
from wisp.settings import Settings, language_code, validate


def read_wav(path) -> tuple[tuple[int, int, int], bytes]:
    with wave.open(str(path)) as wav:
        return (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()), \
            wav.readframes(wav.getnframes())


# ----- debug WAV --------------------------------------------------------------------------------
def test_recorder_writes_exactly_what_was_added(isolated_data_dir):
    enabled = {"on": True}
    recorder = DebugAudioRecorder(lambda: enabled["on"])
    recorder.add(b"\x01\x02" * 100)
    recorder.add(b"\x03\x04" * 50)
    path = recorder.finish()
    assert path.parent == debug_dir() and path.name.startswith("voice-")
    fmt, frames = read_wav(path)
    assert fmt == (16000, 1, 2) and frames == b"\x01\x02" * 100 + b"\x03\x04" * 50
    enabled["on"] = False
    recorder.add(b"\x01\x00" * 10)
    assert recorder.finish() is None


def test_prune_keeps_the_newest(isolated_data_dir):
    names = {save_pcm("t", b"\x00\x00").name for _ in range(25)}
    assert len(names) == 25  # unique even within one millisecond
    prune(debug_dir(), keep=20)
    assert len(list(debug_dir().glob("*.wav"))) == 20


async def test_session_saves_the_exact_bytes_sent(db, isolated_data_dir):
    server = FakeLiveServer()
    recorder = DebugAudioRecorder(lambda: True)
    manager = LiveSessionManager(
        asyncio.get_running_loop(), server, lambda handle: SimpleNamespace(),
        None, LiveCallbacks(), has_key=lambda: True, idle_timeout_s=lambda: 3600,
        always_listening=lambda: False, tick_s=0.02, debug_audio=recorder)
    manager.begin_turn()
    speak(manager, chunks=8)
    manager.end_turn()
    await until(lambda: list(debug_dir().glob("voice-*.wav")))
    _fmt, frames = read_wav(next(debug_dir().glob("voice-*.wav")))
    sent = b"".join(v.data for k, v in server.current.sent if k == "audio")
    assert frames == sent == SPEECH_CHUNK * 8
    manager.disconnect()


# ----- language lock (D-040) --------------------------------------------------------------------
def test_default_language_is_english_uk_with_a_firm_rule():
    settings = Settings()
    assert settings.ai.language == "English (UK)" and language_code("English (UK)") == "en-GB"
    text = system_instruction(settings, [], datetime(2026, 10, 13, 9, 0))
    assert language_rule("English (UK)") in text
    assert "always reply in English (UK)" in text and "explicitly asks" in text


def test_transcription_gets_a_language_hint():
    settings = Settings()
    config = build_live_config(settings, [], "x", None)
    assert config.input_audio_transcription.language_codes == ["en-GB"]
    assert config.output_audio_transcription.language_codes == ["en-GB"]
    settings.ai.language = "Klingon"  # free text: rule only, no code
    assert build_live_config(settings, [], "x", None).input_audio_transcription.language_codes \
        is None
    settings.ai.language = "  "
    assert any("Language" in p for p in validate(settings))


def test_old_settings_value_still_works():
    assert language_code("English") == "en"


# ----- capture through a fake sound device ------------------------------------------------------
class FakeStream:
    def __init__(self, callback):
        self.callback = callback

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


@pytest.fixture
def fake_sd(monkeypatch):
    import sounddevice as sd

    opened = []

    def raw_input_stream(**kwargs):
        opened.append(kwargs)
        return FakeStream(kwargs["callback"])

    monkeypatch.setattr(sd, "query_devices", lambda device=None, kind=None: {
        "default_samplerate": 48000.0, "max_input_channels": 4, "name": "Array"})
    monkeypatch.setattr(sd, "check_input_settings", lambda **kwargs: None)
    monkeypatch.setattr(sd, "RawInputStream", raw_input_stream)
    return opened


def test_native_4ch_48k_float_capture_reaches_subscribers_as_16k_mono(fake_sd):
    from wisp.audio.capture import MicCapture

    mic = MicCapture(lambda: "")
    got = []
    try:
        mic.acquire("t")
        mic.subscribe("t", got.append)
        settings = fake_sd[0]
        assert (settings["samplerate"], settings["channels"], settings["dtype"]) == (
            48000, 4, "float32")
        assert mic.format_description == "48000 Hz × 4 ch float32"
        t = np.arange(48000) / 48000
        voice = (0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
        frames = np.stack([voice, voice, np.zeros_like(voice), np.zeros_like(voice)], axis=1)
        raw = frames.astype("<f4").tobytes()
        callback = mic._stream.callback
        for start in range(0, len(raw), 1536 * 16):
            callback(raw[start:start + 1536 * 16], 1536, None, None)
        deadline = time.monotonic() + 2
        while sum(map(len, got)) < 31000 and time.monotonic() < deadline:
            time.sleep(0.01)
        pcm = b"".join(got)
        assert abs(len(pcm) // 2 - 16000) <= 2  # 1 s at 16 kHz mono int16
        level = 20 * np.log10(np.sqrt(np.mean((np.frombuffer(pcm, "<i2")[4000:] / 32768) ** 2)))
        assert level == pytest.approx(20 * np.log10(0.3 / np.sqrt(2)), abs=0.7)
        assert mic.channel_levels()[2] == -120.0
        assert len(mic.preroll(300)) == 16000 * 2 * 300 // 1000
    finally:
        mic.close()


def test_device_refusing_native_format_falls_back_to_16k_mono(fake_sd, monkeypatch):
    import sounddevice as sd

    from wisp.audio.capture import MicCapture

    def picky(**kwargs):
        if kwargs.get("dtype") == "float32":
            raise ValueError("Invalid sample format")

    monkeypatch.setattr(sd, "check_input_settings", picky)
    mic = MicCapture(lambda: "")
    try:
        mic.acquire("t")
        assert (fake_sd[0]["samplerate"], fake_sd[0]["channels"], fake_sd[0]["dtype"]) == (
            16000, 1, "int16")
    finally:
        mic.close()


# ----- microphone test report ---------------------------------------------------------------------
def test_mic_test_report_in_plain_english(isolated_data_dir):
    from wisp.ui.settings.hotkeys_audio_page import describe_mic_test

    speech = SPEECH_CHUNK * 50
    saved = save_pcm("mic-test", speech)
    report = describe_mic_test(speech, "44100 Hz × 4 ch float32", [-30.0, -31.0, -120.0, -120.0],
                               saved)
    assert report.startswith("Speech heard") and "44100 Hz × 4 ch" in report
    assert "-30, -31, -120, -120" in report and saved.name in report
    assert "silent" in describe_mic_test(b"\x00\x00" * 16000, "", [], None)
    assert "No audio arrived" in describe_mic_test(b"", "", [], None)


@pytest.mark.qt
def test_debug_switch_round_trip(qtbot, tmp_path):
    from wisp.settings import SettingsStore
    from wisp.ui.settings.dialog import SettingsDialog
    from wisp.ui.settings.hotkeys_audio_page import HotkeysAudioPage

    store = SettingsStore(tmp_path / "s.json")
    page = HotkeysAudioPage()
    dialog = SettingsDialog(store, [page])
    qtbot.addWidget(dialog)
    dialog.open_page("Hotkeys and audio")
    assert not page.save_debug.isChecked() and not page.test_button.isEnabled()  # no mic given
    page.save_debug.setChecked(True)
    assert dialog.apply()
    assert SettingsStore(store.path).get().audio.save_debug_audio is True


def test_old_plain_english_setting_becomes_english_uk():
    loaded = Settings.from_dict({"ai": {"language": "English"}})
    assert loaded.ai.language == "English (UK)"
    assert Settings.from_dict({"ai": {"language": "English (US)"}}).ai.language == "English (US)"
