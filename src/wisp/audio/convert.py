"""Convert microphone audio in any device format to what the Live API expects: raw 16-bit
little-endian PCM, mono, 16 kHz (ai.google.dev/gemini-api/docs/live-api/capabilities; sent with
``audio/pcm;rate=16000``). DECISIONS.md D-039.

* **Sample type:** float32 (−1…1) or int16 input; output is int16, clipped, never float bytes.
* **Channels:** laptop "microphone arrays" can expose 2–4 raw channels, some of them silent or
  much quieter (unused or reference channels). Averaging them all would lower the level and
  blur speech, so only the *active* channels are averaged: those within 10 dB of the loudest,
  judged on a smoothed power estimate so the choice doesn't flap between chunks.
* **Rate:** a windowed-sinc (Blackman) low-pass at 7 kHz removes everything the 16 kHz output
  can't represent, then linear interpolation picks the output samples (exact decimation for
  48 kHz). Filter and interpolation keep state across chunks, so there are no clicks.
"""

from __future__ import annotations

import numpy as np

from wisp.audio import INPUT_RATE

CUTOFF_HZ = 7000.0
ACTIVE_WITHIN_DB = 10.0
POWER_SMOOTHING = 0.8  # weight of the previous estimate (chunks are ~10–40 ms)


def lowpass_taps(src_rate: int, cutoff: float = CUTOFF_HZ) -> np.ndarray:
    """Blackman-windowed sinc; about 40 taps per 16 kHz of source rate (odd length)."""
    count = int(src_rate / INPUT_RATE * 40) | 1
    n = np.arange(count) - (count - 1) / 2
    taps = np.sinc(2 * cutoff / src_rate * n) * np.blackman(count)
    return (taps / taps.sum()).astype(np.float32)


def rms_dbfs(samples: np.ndarray) -> float:
    """Level of float samples (full scale = 1.0) in dBFS; −120 for silence."""
    if samples.size == 0:
        return -120.0
    power = float(np.mean(np.square(samples, dtype=np.float64)))
    return 10 * np.log10(power) if power > 1e-12 else -120.0


class MicConverter:
    """Streaming converter: device chunks in, 16 kHz mono int16 bytes out."""

    def __init__(self, src_rate: int, channels: int, dtype: str = "int16"):
        if src_rate <= 0 or channels <= 0:
            raise ValueError("Sample rate and channel count must be positive")
        if dtype not in ("int16", "float32"):
            raise ValueError(f"Unsupported sample type {dtype}")
        self.src_rate = src_rate
        self.channels = channels
        self.dtype = dtype
        self._ratio = src_rate / INPUT_RATE
        self._power = np.zeros(channels, dtype=np.float64)
        self.active = np.ones(channels, dtype=bool)
        self._taps = lowpass_taps(src_rate) if src_rate > INPUT_RATE else None
        self._history = np.zeros(len(self._taps) - 1 if self._taps is not None else 0,
                                 dtype=np.float32)
        self._pending = np.zeros(0, dtype=np.float32)
        self._pos = 0.0

    @property
    def passthrough(self) -> bool:
        return self.src_rate == INPUT_RATE and self.channels == 1 and self.dtype == "int16"

    def channel_levels(self) -> list[float]:
        """Smoothed level of each input channel in dBFS (for diagnostics)."""
        return [round(float(10 * np.log10(p)), 1) if p > 1e-12 else -120.0
                for p in self._power]

    def process(self, raw: bytes) -> bytes:
        if self.passthrough:
            return raw
        if self.dtype == "int16":
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        else:
            samples = np.frombuffer(raw, dtype="<f4").astype(np.float32)
        usable = len(samples) - len(samples) % self.channels
        frames = samples[:usable].reshape(-1, self.channels)
        mono = self._downmix(frames)
        if self.src_rate != INPUT_RATE:
            mono = self._resample(mono)
        return np.clip(np.round(mono * 32767.0), -32768, 32767).astype("<i2").tobytes()

    # ----- steps -------------------------------------------------------------------------------
    def _downmix(self, frames: np.ndarray) -> np.ndarray:
        if self.channels == 1:
            return frames[:, 0]
        if len(frames):
            power = np.mean(np.square(frames, dtype=np.float64), axis=0)
            self._power = POWER_SMOOTHING * self._power + (1 - POWER_SMOOTHING) * power
        loudest = float(self._power.max())
        if loudest > 1e-12:
            self.active = self._power >= loudest * 10 ** (-ACTIVE_WITHIN_DB / 10)
        else:
            self.active = np.ones(self.channels, dtype=bool)
        return frames[:, self.active].mean(axis=1).astype(np.float32)

    def _resample(self, mono: np.ndarray) -> np.ndarray:
        if self._taps is not None:
            padded = np.concatenate([self._history, mono])
            filtered = np.convolve(padded, self._taps, mode="valid").astype(np.float32)
            self._history = padded[len(padded) - (len(self._taps) - 1):]
            mono = filtered
        data = np.concatenate([self._pending, mono])
        if len(data) < 2:
            self._pending = data
            return np.zeros(0, dtype=np.float32)
        positions = np.arange(self._pos, len(data) - 1, self._ratio)
        out = np.interp(positions, np.arange(len(data)), data).astype(np.float32)
        next_pos = (positions[-1] + self._ratio) if len(positions) else self._pos
        keep_from = int(np.floor(next_pos))
        self._pending = data[keep_from:]
        self._pos = next_pos - keep_from
        return out


SPEECH_DBFS = -45.0
"""A 32 ms frame at least this loud means someone is speaking; a quiet room is around −60 dBFS
and silence makes the transcriber invent short phrases in random languages (D-039)."""


def has_speech(pcm: bytes, threshold_dbfs: float = SPEECH_DBFS) -> bool:
    """True if any 32 ms frame of 16 kHz int16 audio reaches ``threshold_dbfs``."""
    samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype="<i2").astype(np.float32)
    frame = INPUT_RATE * 32 // 1000
    for start in range(0, len(samples), frame):
        if rms_dbfs(samples[start:start + frame] / 32768.0) >= threshold_dbfs:
            return True
    return False
