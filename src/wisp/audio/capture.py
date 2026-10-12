"""Microphone capture: opened on demand, shared by voice, dictation and Circle to Ask.

The PortAudio callback only copies bytes into a queue (it must never block); a delivery thread
fans chunks out to subscribers. A short pre-roll keeps the last ~0.5 s so words spoken while a
hold-hotkey is still arming are not lost.
"""

from __future__ import annotations

import collections
import logging
import queue
import threading
from collections.abc import Callable

import numpy as np

from wisp.audio import INPUT_RATE
from wisp.audio.devices import resolve
from wisp.audio.resample import Resampler

log = logging.getLogger(__name__)

CHUNK_FRAMES = 512  # 32 ms at 16 kHz
PREROLL_CHUNKS = 16  # ~0.5 s

MIC_HELP = (
    "Microphone unavailable. Check that a mic is connected and that Windows Settings → "
    "Privacy & security → Microphone → 'Let desktop apps access your microphone' is on."
)


class MicError(RuntimeError):
    pass


class MicCapture:
    def __init__(self, device_name: Callable[[], str]):
        self._device_name = device_name
        self._lock = threading.RLock()
        self._users: set[str] = set()
        self._subscribers: dict[str, Callable[[bytes], None]] = {}
        self._stream = None
        self._resampler: Resampler | None = None
        self._queue: queue.SimpleQueue[bytes | None] = queue.SimpleQueue()
        self._preroll: collections.deque[bytes] = collections.deque(maxlen=PREROLL_CHUNKS)
        self._muted = False
        self.level = 0.0
        self._worker = threading.Thread(target=self._deliver, name="mic-delivery", daemon=True)
        self._worker.start()

    # ----- public API ------------------------------------------------------------------------
    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            self._muted = muted
            if muted:
                self._close_stream()
            elif self._users:
                self._open_stream()

    def acquire(self, user: str) -> None:
        """Start capturing for ``user``; raises MicError if the mic cannot be opened."""
        with self._lock:
            if self._muted:
                raise MicError("Microphone is muted in Wisp.")
            self._users.add(user)
            if self._stream is None:
                try:
                    self._open_stream()
                except MicError:
                    self._users.discard(user)
                    raise

    def release(self, user: str) -> None:
        with self._lock:
            self._users.discard(user)
            if not self._users:
                self._close_stream()

    def subscribe(self, name: str, callback: Callable[[bytes], None]) -> None:
        with self._lock:
            self._subscribers[name] = callback

    def unsubscribe(self, name: str) -> None:
        with self._lock:
            self._subscribers.pop(name, None)

    def preroll(self) -> bytes:
        with self._lock:
            return b"".join(self._preroll)

    def reopen(self) -> None:
        """Re-open on a new device after the setting changes."""
        with self._lock:
            if self._stream is not None:
                self._close_stream()
                self._open_stream()

    def close(self) -> None:
        with self._lock:
            self._users.clear()
            self._close_stream()
        self._queue.put(None)

    # ----- stream handling -------------------------------------------------------------------
    def _open_stream(self) -> None:
        import sounddevice as sd

        device = resolve(self._device_name(), "input")
        rate = INPUT_RATE
        try:
            sd.check_input_settings(device=device, samplerate=INPUT_RATE, channels=1, dtype="int16")
        except Exception:
            info = sd.query_devices(device if device is not None else sd.default.device[0])
            rate = int(info["default_samplerate"])
            log.info("Mic rejects 16 kHz; capturing at %d Hz and resampling", rate)
        self._resampler = Resampler(rate, INPUT_RATE)
        frames = int(CHUNK_FRAMES * rate / INPUT_RATE)
        try:
            stream = sd.RawInputStream(
                samplerate=rate,
                blocksize=frames,
                device=device,
                channels=1,
                dtype="int16",
                callback=self._callback,
            )
            stream.start()
        except Exception as exc:
            log.error("Opening microphone failed: %s", exc)
            raise MicError(MIC_HELP) from exc
        self._stream = stream
        self._preroll.clear()
        log.info("Microphone opened (device=%s, %d Hz)", device, rate)

    def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                log.warning("Closing microphone: %s", exc)
            self.level = 0.0
            log.info("Microphone closed")

    def _callback(self, indata, frames, time_info, status) -> None:
        self._queue.put(bytes(indata))

    def _deliver(self) -> None:
        while True:
            chunk = self._queue.get()
            if chunk is None:
                return
            resampler = self._resampler
            if resampler is not None and not resampler.passthrough:
                chunk = resampler.process(chunk)
            if not chunk:
                continue
            samples = np.frombuffer(chunk, dtype=np.int16)
            self.level = min(1.0, float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) / 6000)
            with self._lock:
                self._preroll.append(chunk)
                subscribers = list(self._subscribers.values())
            for callback in subscribers:
                try:
                    callback(chunk)
                except Exception:
                    log.exception("Mic subscriber failed")
