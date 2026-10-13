"""D-039: microphone audio in any format → 16 kHz mono int16, as the Live API requires."""

from __future__ import annotations

import numpy as np
import pytest

from wisp.audio.convert import MicConverter, has_speech, lowpass_taps, rms_dbfs

OUT_RATE = 16000


def tone(freq: float, rate: int, seconds: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def convert_in_chunks(converter: MicConverter, raw: bytes, frame_bytes: int,
                      chunk_frames: int) -> np.ndarray:
    out = bytearray()
    step = frame_bytes * chunk_frames
    for start in range(0, len(raw), step):
        out += converter.process(raw[start:start + step])
    return np.frombuffer(bytes(out), dtype="<i2")


def dominant_hz(samples: np.ndarray, rate: int = OUT_RATE) -> float:
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    return float(np.fft.rfftfreq(len(samples), 1 / rate)[np.argmax(spectrum)])


def test_48k_stereo_float32_becomes_16k_mono_int16():
    """The brief's check: a known 48 kHz stereo float32 signal through the conversion."""
    signal = tone(1000, 48000, 1.0)
    stereo = np.stack([signal, signal], axis=1).astype("<f4")  # interleaved L R
    converter = MicConverter(48000, 2, "float32")
    out = convert_in_chunks(converter, stereo.tobytes(), frame_bytes=8, chunk_frames=1536)
    assert out.dtype == np.dtype("<i2")
    assert abs(len(out) - OUT_RATE) <= 1  # 1 s at 16 kHz (not 3 s, not 0.33 s)
    steady = out[800:-800].astype(np.float32) / 32768
    assert dominant_hz(steady) == pytest.approx(1000, abs=5)  # not sped up or slowed down
    assert rms_dbfs(steady) == pytest.approx(rms_dbfs(signal), abs=0.5)  # same loudness
    assert not converter.passthrough


def test_quiet_or_dead_array_channels_dont_lower_the_level():
    """A 4-channel laptop array with two silent channels: average only the live ones."""
    voice = tone(440, 48000, 0.6, amplitude=0.3)
    silent = np.zeros_like(voice)
    frames = np.stack([voice, voice, silent, silent], axis=1).astype("<f4")
    converter = MicConverter(48000, 4, "float32")
    out = convert_in_chunks(converter, frames.tobytes(), frame_bytes=16, chunk_frames=1536)
    steady = out[2000:].astype(np.float32) / 32768
    assert rms_dbfs(steady) == pytest.approx(rms_dbfs(voice), abs=0.5)  # not 6 dB lower
    assert list(converter.active) == [True, True, False, False]
    assert converter.channel_levels()[2] == -120.0


def test_anti_aliasing_removes_what_16k_cannot_hold():
    high = tone(12000, 48000, 0.5)  # would fold to 4 kHz without filtering
    out = convert_in_chunks(MicConverter(48000, 1, "float32"), high.astype("<f4").tobytes(),
                            frame_bytes=4, chunk_frames=1536)
    assert rms_dbfs(out[200:].astype(np.float32) / 32768) < rms_dbfs(high) - 40


def test_44100_int16_and_chunking_is_seamless():
    signal = tone(500, 44100, 1.0)
    raw = (signal * 32767).astype("<i2").tobytes()
    whole = np.frombuffer(MicConverter(44100, 1, "int16").process(raw), dtype="<i2")
    chunked = convert_in_chunks(MicConverter(44100, 1, "int16"), raw, frame_bytes=2,
                                chunk_frames=441)
    assert abs(len(chunked) - OUT_RATE) <= 1 and abs(len(whole) - len(chunked)) <= 1
    n = min(len(whole), len(chunked))
    assert np.max(np.abs(whole[:n].astype(int) - chunked[:n].astype(int))) <= 2  # no clicks
    assert dominant_hz(chunked[400:-400].astype(np.float32)) == pytest.approx(500, abs=5)


def test_16k_mono_int16_passes_through_unchanged():
    raw = (tone(300, 16000, 0.1) * 32767).astype("<i2").tobytes()
    converter = MicConverter(16000, 1, "int16")
    assert converter.passthrough and converter.process(raw) == raw


def test_float_is_never_sent_as_int16_and_clips_safely():
    loud = np.full(4800, 1.7, dtype="<f4")  # out-of-range float input
    out = np.frombuffer(MicConverter(48000, 1, "float32").process(loud.tobytes()), dtype="<i2")
    assert len(out) * 2 == len(out.tobytes()) and out.max() <= 32767 and out.min() >= -32768


def test_bad_formats_are_refused():
    with pytest.raises(ValueError):
        MicConverter(0, 1)
    with pytest.raises(ValueError):
        MicConverter(48000, 2, "int24")


def test_lowpass_is_normalised_and_symmetric():
    taps = lowpass_taps(48000)
    assert len(taps) % 2 == 1 and taps.sum() == pytest.approx(1.0)
    assert np.allclose(taps, taps[::-1])


def test_has_speech():
    silence = b"\x00\x00" * 16000
    room = (np.random.default_rng(0).standard_normal(16000) * 30).astype("<i2").tobytes()
    word = (tone(200, 16000, 0.2, amplitude=0.05) * 32767).astype("<i2").tobytes()
    assert not has_speech(silence) and not has_speech(room)  # ≈ -60 dBFS hiss is not speech
    assert has_speech(silence + word)
