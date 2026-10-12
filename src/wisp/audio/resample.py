"""Streaming int16 mono resampler, used only when a device rejects the Live API rates.

Windows' MME layer normally resamples for us (proven by ``spikes/audio_formats.py``); this is
the fallback for devices that refuse 16/24 kHz. Downsampling applies a short moving-average
low-pass first to limit aliasing, then linear interpolation; both keep state across chunks so
there are no clicks at chunk boundaries.
"""

from __future__ import annotations

import numpy as np


class Resampler:
    def __init__(self, src_rate: int, dst_rate: int):
        if src_rate <= 0 or dst_rate <= 0:
            raise ValueError("Sample rates must be positive")
        self.src_rate = src_rate
        self.dst_rate = dst_rate
        self._ratio = src_rate / dst_rate
        self._pos = 0.0  # fractional read position into the pending source samples
        self._pending = np.zeros(0, dtype=np.float32)
        taps = max(1, round(self._ratio)) if src_rate > dst_rate else 1
        self._kernel = np.ones(taps, dtype=np.float32) / taps
        self._history = np.zeros(taps - 1, dtype=np.float32)

    @property
    def passthrough(self) -> bool:
        return self.src_rate == self.dst_rate

    def process(self, pcm: bytes) -> bytes:
        if self.passthrough:
            return pcm
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if len(self._kernel) > 1:
            padded = np.concatenate([self._history, samples])
            filtered = np.convolve(padded, self._kernel, mode="valid")
            self._history = padded[len(padded) - (len(self._kernel) - 1):]
            samples = filtered
        data = np.concatenate([self._pending, samples])
        if len(data) < 2:
            self._pending = data
            return b""
        positions = np.arange(self._pos, len(data) - 1, self._ratio)
        out = np.interp(positions, np.arange(len(data)), data)
        next_pos = (positions[-1] + self._ratio) if len(positions) else self._pos
        keep_from = int(np.floor(next_pos))
        self._pending = data[keep_from:]
        self._pos = next_pos - keep_from
        return np.clip(np.round(out), -32768, 32767).astype(np.int16).tobytes()
