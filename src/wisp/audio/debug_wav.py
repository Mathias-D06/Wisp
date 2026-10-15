"""Troubleshooting aid (Settings → Hotkeys and audio → "Save the audio and screenshots sent to
Gemini"): writes exactly the PCM bytes Wisp sends to Gemini as WAV files in
%APPDATA%\\Wisp\\debug, so the user can listen to what the model heard, and Screen Assist's
screenshots as JPEGs. Off by default; the newest 20 of each are kept.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import wave
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from wisp import paths
from wisp.audio import INPUT_RATE

log = logging.getLogger(__name__)

KEEP_FILES = 20
MAX_SECONDS = 120


def debug_dir() -> Path:
    folder = paths.data_dir() / "debug"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_wav(path: Path, pcm: bytes, rate: int = INPUT_RATE) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return path


def prune(folder: Path, keep: int = KEEP_FILES, pattern: str = "*.wav") -> None:
    files = sorted(folder.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        with contextlib.suppress(OSError):
            old.unlink()


def save_pcm(label: str, pcm: bytes, rate: int = INPUT_RATE) -> Path | None:
    """Save one clip now (dictation, microphone test)."""
    if not pcm:
        return None
    folder = debug_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    path = folder / f"{label}-{stamp}.wav"
    counter = 1
    while path.exists():  # two clips in the same millisecond must not overwrite each other
        path = folder / f"{label}-{stamp}-{counter}.wav"
        counter += 1
    path = write_wav(path, pcm, rate)
    prune(folder)
    log.info("Saved %s (%.1f s) for troubleshooting", path.name, len(pcm) / (rate * 2))
    return path


def save_jpeg(label: str, data: bytes) -> Path | None:
    """Save a screenshot exactly as sent to Gemini (Screen Assist, D-052); newest 20 kept."""
    if not data:
        return None
    folder = debug_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    path = folder / f"{label}-{stamp}.jpg"
    path.write_bytes(data)
    prune(folder, pattern="*.jpg")
    log.info("Saved %s for troubleshooting", path.name)
    return path


class DebugAudioRecorder:
    """Collects the audio of one voice turn as it is sent; ``finish`` writes it out."""

    def __init__(self, enabled: Callable[[], bool], label: str = "voice"):
        self._enabled = enabled
        self._label = label
        self._lock = threading.Lock()
        self._buffer = bytearray()

    def add(self, pcm: bytes) -> None:
        if not self._enabled():
            return
        with self._lock:
            if len(self._buffer) < INPUT_RATE * 2 * MAX_SECONDS:
                self._buffer.extend(pcm)

    def finish(self) -> Path | None:
        with self._lock:
            pcm, self._buffer = bytes(self._buffer), bytearray()
        if not pcm or not self._enabled():
            return None
        try:
            return save_pcm(self._label, pcm)
        except OSError as exc:
            log.warning("Could not save debug audio: %s", exc)
            return None
