"""Speaker playback of the model's 24 kHz PCM with instant clearing for barge-in.

The PortAudio callback fills ``outdata`` completely on every call (zeros when the buffer is
empty), as the sounddevice docs require. ``clear()`` drops queued audio so playback stops within
one callback period.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import numpy as np

from wisp.audio import OUTPUT_RATE
from wisp.audio.devices import resolve
from wisp.audio.resample import Resampler

log = logging.getLogger(__name__)

IDLE_CLOSE_SECONDS = 15.0


class Player:
    def __init__(self, device_name: Callable[[], str]):
        self._device_name = device_name
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._stream = None
        self._resampler: Resampler | None = None
        self._last_audio = 0.0
        self.level = 0.0
        self._closer = threading.Thread(target=self._idle_closer, name="player-idle", daemon=True)
        self._stop = threading.Event()
        self._closer.start()

    def feed(self, pcm: bytes) -> None:
        if not pcm:
            return
        try:
            self._ensure_stream()
        except Exception as exc:
            log.error("Opening speaker failed: %s", exc)
            return
        resampler = self._resampler
        if resampler is not None and not resampler.passthrough:
            pcm = resampler.process(pcm)
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size:
            self.level = min(1.0, float(np.abs(samples).mean()) / 4000)
        with self._lock:
            self._buffer.extend(pcm)
            self._last_audio = time.monotonic()

    def clear(self) -> None:
        """Stop speaking now (barge-in)."""
        with self._lock:
            self._buffer.clear()
        self.level = 0.0

    def is_playing(self) -> bool:
        with self._lock:
            return len(self._buffer) > 0

    def reopen(self) -> None:
        with self._lock:
            stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()

    def close(self) -> None:
        self._stop.set()
        self.clear()
        self.reopen()

    def _ensure_stream(self) -> None:
        if self._stream is not None:
            return
        import sounddevice as sd

        device = resolve(self._device_name(), "output")
        rate = OUTPUT_RATE
        try:
            sd.check_output_settings(
                device=device, samplerate=OUTPUT_RATE, channels=1, dtype="int16"
            )
        except Exception:
            info = sd.query_devices(device if device is not None else sd.default.device[1])
            rate = int(info["default_samplerate"])
            log.info("Speaker rejects 24 kHz; playing at %d Hz with resampling", rate)
        self._resampler = Resampler(OUTPUT_RATE, rate)
        stream = sd.RawOutputStream(
            samplerate=rate, device=device, channels=1, dtype="int16",
            latency="low", callback=self._callback,
        )
        stream.start()
        self._stream = stream
        log.info("Speaker opened (device=%s, %d Hz)", device, rate)

    def _callback(self, outdata, frames, time_info, status) -> None:
        needed = frames * 2
        with self._lock:
            take = min(needed, len(self._buffer))
            chunk = bytes(self._buffer[:take])
            del self._buffer[:take]
        if take < needed:
            chunk += b"\x00" * (needed - take)
            if take == 0:
                self.level = 0.0
        outdata[:] = chunk

    def _idle_closer(self) -> None:
        while not self._stop.wait(2.0):
            with self._lock:
                idle = (
                    self._stream is not None
                    and not self._buffer
                    and time.monotonic() - self._last_audio > IDLE_CLOSE_SECONDS
                )
            if idle:
                self.reopen()
                log.info("Speaker closed after idle")
