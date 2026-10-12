from __future__ import annotations

from datetime import datetime

import numpy as np
from google.genai import _live_converters, types

from wisp.audio.resample import Resampler
from wisp.live.config import build_live_config, is_extended_thinking, system_instruction
from wisp.settings import Settings

DECLS = [{"name": "open_app", "description": "Open an app",
          "parameters": {"type": "object", "properties": {
              "name": {"type": "string", "description": "app"}}, "required": ["name"]}}]


def _tone(rate: int, seconds: float, freq: float = 440.0) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    return (np.sin(2 * np.pi * freq * t) * 10000).astype(np.int16).tobytes()


def test_resampler_ratio_and_continuity():
    resampler = Resampler(48000, 16000)
    source = _tone(48000, 1.0)
    out = b"".join(resampler.process(source[i:i + 3072]) for i in range(0, len(source), 3072))
    samples = np.frombuffer(out, dtype=np.int16)
    assert abs(len(samples) - 16000) <= 3
    # A clean 440 Hz tone stays smooth: no large jumps at chunk boundaries.
    assert np.max(np.abs(np.diff(samples.astype(np.int32)))) < 2000


def test_resampler_upsample_and_passthrough():
    up = Resampler(24000, 48000)
    out = up.process(_tone(24000, 0.5))
    assert abs(len(out) // 2 - 24000) <= 3
    same = Resampler(16000, 16000)
    data = _tone(16000, 0.1)
    assert same.process(data) is data


def _setup_json(config) -> dict:
    parent: dict = {}
    _live_converters._LiveConnectConfig_to_mldev(
        api_client=None, from_object=config.model_dump(exclude_none=True), parent_object=parent)
    return parent["setup"]


def test_push_to_talk_config_disables_server_vad():
    config = build_live_config(Settings(), DECLS, "sys", None)
    assert config.realtime_input_config.automatic_activity_detection.disabled is True
    assert config.context_window_compression.sliding_window is not None
    assert config.session_resumption.handle is None
    assert config.response_modalities == ["AUDIO"]
    setup = _setup_json(config)
    for key in ("contextWindowCompression", "sessionResumption", "realtimeInputConfig",
                "inputAudioTranscription", "outputAudioTranscription", "tools"):
        assert key in setup


def test_always_listening_and_resume_handle():
    settings = Settings()
    settings.audio.always_listening = True
    settings.loadout.voice = "Puck"
    config = build_live_config(settings, DECLS, "sys", "handle-123")
    vad = config.realtime_input_config.automatic_activity_detection
    assert vad.disabled is False and 500 <= vad.silence_duration_ms <= 800
    assert config.session_resumption.handle == "handle-123"
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Puck"


def test_extended_thinking_marks_tools_non_blocking():
    settings = Settings()
    settings.ai.live_model = "gemini-3.8-live-extended-thinking"
    assert is_extended_thinking(settings.ai.live_model)
    config = build_live_config(settings, DECLS, "sys", None)
    assert config.tools[0].function_declarations[0].behavior == types.Behavior.NON_BLOCKING
    default = build_live_config(Settings(), DECLS, "sys", None)
    assert default.tools[0].function_declarations[0].behavior is None


def test_system_instruction_is_short_and_has_rules():
    settings = Settings()
    settings.loadout.personality = "custom"
    settings.loadout.custom_personality = "Talk like a pirate"
    text = system_instruction(settings, ["Sister's birthday is 3 May"],
                              datetime(2026, 10, 12, 9, 30))
    assert "Talk like a pirate" in text
    assert "untrusted_content" in text and "confirm_action" in text
    assert "Sister's birthday is 3 May" in text
    assert "Monday 12 October 2026, 09:30" in text
    assert len(text) < 1800  # keep the per-session token cost low
