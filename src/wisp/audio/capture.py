"""Microphone capture: opened on demand, shared by voice, dictation and Circle to Ask.

The stream opens in the device's own format when it supports it (native rate and channel count,
float32) and ``MicConverter`` turns that into 16 kHz mono int16 — so Wisp, not Windows, decides
how a multi-channel microphone array is mixed (D-039). Devices that refuse their native format
fall back to asking Windows for 16 kHz mono int16 directly (D-007).

The PortAudio callback only copies bytes into a queue (it must never block); a delivery thread
converts and fans chunks out to subscribers. A pre-roll keeps the last ~0.5 s so the words
spoken while the push-to-talk keys are still arming are sent too.
"""

from __future__ import annotations

import collections
import logging
import queue
import threading
import time
from collections.abc import Callable

import numpy as np

from wisp.audio import INPUT_RATE, mic_check
from wisp.audio.convert import MicConverter, rms_dbfs
from wisp.audio.devices import resolve

log = logging.getLogger(__name__)

CHUNK_MS = 32
PREROLL_CHUNKS = 16  # ~0.5 s
MAX_CHANNELS = 8
LEVEL_LOG_AFTER_S = 1.0

MIC_HELP = (
    "Microphone unavailable. Check that a mic is connected and that Windows Settings → "
    "Privacy & security → Microphone → 'Let desktop apps access your microphone' is on."
)


class MicError(RuntimeError):
    pass


class MicCapture:
    def __init__(self, device_name: Callable[[], str]):
        self._device_name = device_name
        self._lock = threading.RLock()  # the stream; held while it opens (can take a second)
        # subscribers and pre-roll: never held for long, so subscribing or unsubscribing doesn't
        # wait for a stream that is opening on another thread (D-058)
        self._subs_lock = threading.Lock()
        self._users: set[str] = set()
        self._subscribers: dict[str, Callable[[bytes], None]] = {}
        self._stream = None
        self._converter: MicConverter | None = None
        self.format_description = ""
        self.device_label = ""  # the device's name, once opened
        self._converted_bytes = 0
        self._levels_logged = False
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
        with self._subs_lock:
            self._subscribers[name] = callback

    def unsubscribe(self, name: str) -> None:
        with self._subs_lock:
            self._subscribers.pop(name, None)

    def preroll(self, ms: int | None = None) -> bytes:
        """The most recent captured audio (16 kHz mono int16); all of it, or the last ``ms``."""
        with self._subs_lock:
            data = b"".join(self._preroll)
        if ms is not None:
            keep = INPUT_RATE * 2 * ms // 1000
            data = data[-keep:] if keep else b""
        return data

    def warm_up(self) -> None:
        """Start PortAudio and look the input device up ahead of the first use: on the first
        Screen Assist hotkey that took over a second (D-058). Opens no stream, so nothing is
        recorded and Windows shows no microphone-in-use indicator."""
        started = time.monotonic()
        try:
            with self._lock:
                import sounddevice as sd

                device = resolve(self._device_name(), "input")
                info = sd.query_devices(device if device is not None else sd.default.device[0])
        except Exception as exc:  # no audio devices: acquire() reports it when needed
            log.info("Audio warm-up skipped: %s", exc)
            return
        log.info("Audio ready in %.2f s (input %r; no stream opened)",
                 time.monotonic() - started, info["name"])

    def channel_levels(self) -> list[float]:
        """Level of each device channel (dBFS) while the stream is open, for diagnostics."""
        converter = self._converter
        return converter.channel_levels() if converter is not None else []

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
    def _formats(self, device) -> list[tuple[int, int, str]]:
        """Formats to try: the device's native one first, then 16 kHz mono (Windows converts)."""
        import sounddevice as sd

        info = sd.query_devices(device if device is not None else sd.default.device[0])
        self.device_label = str(info["name"])
        native_rate = int(info["default_samplerate"])
        native_channels = max(1, min(int(info["max_input_channels"]), MAX_CHANNELS))
        candidates = [(native_rate, native_channels, "float32"), (INPUT_RATE, 1, "int16"),
                      (native_rate, 1, "int16")]
        usable = []
        for rate, channels, dtype in dict.fromkeys(candidates):
            try:
                sd.check_input_settings(device=device, samplerate=rate, channels=channels,
                                        dtype=dtype)
            except Exception:
                continue
            usable.append((rate, channels, dtype))
        return usable

    def _open_stream(self) -> None:
        import sounddevice as sd

        device = resolve(self._device_name(), "input")
        try:
            formats = self._formats(device)
        except Exception as exc:
            log.error("Querying the microphone failed: %s", exc)
            raise MicError(MIC_HELP) from exc
        last_error: Exception | None = None
        for rate, channels, dtype in formats:
            frames = max(1, rate * CHUNK_MS // 1000)
            try:
                stream = sd.RawInputStream(samplerate=rate, blocksize=frames, device=device,
                                           channels=channels, dtype=dtype,
                                           callback=self._callback)
                stream.start()
            except Exception as exc:
                last_error = exc
                log.warning("Microphone format %d Hz × %d ch %s failed: %s", rate, channels,
                            dtype, exc)
                continue
            self._converter = MicConverter(rate, channels, dtype)
            self._stream = stream
            with self._subs_lock:
                self._preroll.clear()
            self._converted_bytes = 0
            self._levels_logged = False
            self.format_description = f"{rate} Hz × {channels} ch {dtype}"
            log.info("Microphone opened (%s, device=%s, %s → 16 kHz mono int16)",
                     self.device_label, device, self.format_description)
            return
        log.error("Opening microphone failed: %s", last_error or "no usable format")
        raise MicError(MIC_HELP) from last_error

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

    def _log_levels(self, converter: MicConverter, samples: np.ndarray) -> None:
        """Once per opening, after 1 s: the output level and each channel's, as plain numbers;
        a warning with Windows' microphone privacy switches if every channel is silent."""
        level = rms_dbfs(samples.astype(np.float32) / 32768.0)
        channels = converter.channel_levels()
        used = ", ".join(str(i + 1) for i, on in enumerate(converter.active) if on)
        log.info("Mic levels after 1 s: output %.0f dBFS; channels (dBFS) %s; mixing %s",
                 level, ", ".join(f"{c:.1f}" for c in channels), used)
        if mic_check.channels_silent(channels):
            log.warning("Every channel of %r is silent; Windows microphone privacy: %s",
                        self.device_label, mic_check.describe_states(mic_check.privacy_states()))

    def _callback(self, indata, frames, time_info, status) -> None:
        self._queue.put(bytes(indata))

    def _deliver(self) -> None:
        while True:
            chunk = self._queue.get()
            if chunk is None:
                return
            converter = self._converter
            if converter is not None:
                chunk = converter.process(chunk)
            if not chunk:
                continue
            samples = np.frombuffer(chunk, dtype=np.int16)
            self.level = min(1.0, float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) / 6000)
            self._converted_bytes += len(chunk)
            if (not self._levels_logged and converter is not None
                    and self._converted_bytes >= INPUT_RATE * 2 * LEVEL_LOG_AFTER_S):
                self._levels_logged = True
                self._log_levels(converter, samples)
            with self._subs_lock:
                self._preroll.append(chunk)
                subscribers = list(self._subscribers.values())
            for callback in subscribers:
                try:
                    callback(chunk)
                except Exception:
                    log.exception("Mic subscriber failed")
