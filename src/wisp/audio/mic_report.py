"""``Wisp.exe --mic-check [report.json]``: open the microphone the way the app does, for about
1.5 s, and report what arrived (D-055, MT-116).

The report has the program that asked (python.exe or Wisp.exe: Windows treats each separately),
the device and format, each channel's level, the output's level and peak, whether it was digital
silence, and Windows' three microphone privacy switches. Running it from source and from the exe
tells Windows privacy apart from a muted or wrong input.

Only numbers leave this module: the audio stays in memory and is dropped. Nothing is saved or
sent, and the user's settings are only read (for the chosen input device).
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from wisp.audio import INPUT_RATE, mic_check
from wisp.audio.convert import rms_dbfs

SECONDS = 1.5
USER = "mic-check"


def _input_device() -> str:
    try:
        from wisp import paths
        from wisp.settings import SettingsStore

        return SettingsStore(paths.settings_file()).get().audio.input_device
    except Exception:  # no settings yet: the system default
        return ""


def measure(make_mic: Callable[[], object] | None = None, seconds: float = SECONDS,
            states: Callable[[], list] = mic_check.privacy_states) -> dict:
    """Open, listen for ``seconds``, close; the levels as a dict."""
    if make_mic is None:
        from wisp.audio.capture import MicCapture

        device = _input_device()

        def make_mic():
            return MicCapture(lambda: device)

    mic = make_mic()
    chunks: list[bytes] = []
    result: dict = {"program": sys.executable, "frozen": bool(getattr(sys, "frozen", False)),
                    "privacy": {name: value or "not set" for name, value in states()}}
    try:
        mic.subscribe(USER, chunks.append)
        try:
            mic.acquire(USER)
        except Exception as exc:
            result.update(opened=False, error=str(exc) or type(exc).__name__)
            result["verdict"] = verdict(result, [])
            return result
        time.sleep(seconds)
        result.update(opened=True, device=mic.device_label, format=mic.format_description,
                      channels_dbfs=[round(float(level), 1) for level in mic.channel_levels()])
        mic.unsubscribe(USER)
        mic.release(USER)
    finally:
        mic.close()
    pcm = b"".join(chunks)
    samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype="<i2").astype(np.float32)
    peak = float(np.max(np.abs(samples))) / 32768.0 if samples.size else 0.0
    result.update(
        seconds=round(len(pcm) / (INPUT_RATE * 2), 2),
        output_dbfs=round(rms_dbfs(samples / 32768.0), 1),
        peak_dbfs=round(20 * np.log10(peak), 1) if peak > 0 else -120.0,
        digital_silence=mic_check.is_dead_silence(pcm),
        silent_channels=mic_check.channels_silent(result["channels_dbfs"]))
    blocked = mic_check.blocked_switches(states())
    result["verdict"] = verdict(result, blocked)
    return result


def verdict(result: dict, blocked: list[str]) -> str:
    if not result.get("opened"):
        return f"The microphone didn't open: {result.get('error')}"
    if blocked:
        return "Windows is blocking it: " + ", ".join(blocked) + " is off."
    if result["digital_silence"] or result["silent_channels"]:
        return ("Only silence arrived, with Windows' privacy switches on. Compare with the other "
                "build: if only this one is silent, Windows treats this program differently; "
                "if both are, the input is muted, disabled or the wrong one.")
    return "Sound arrived: the microphone works for this program."


def run(report: Path | None = None) -> int:
    result = measure()
    text = json.dumps(result, indent=2)
    if report is not None:
        report.write_text(text, encoding="utf-8")
    if sys.stdout is not None:
        print(text)
    silent = result.get("digital_silence") or result.get("silent_channels")
    return 0 if result.get("opened") and not silent else 1
