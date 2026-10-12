"""Audio device discovery (sounddevice / PortAudio).

Wisp uses the default host API (MME on Windows), which accepts the Live API's 16 kHz input and
24 kHz output directly because the Windows audio engine resamples (``spikes/audio_formats.py``).
Devices are stored in Settings by name; an empty name means the system default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    is_default: bool


def _default_hostapi() -> int:
    import sounddevice as sd

    default_in, _default_out = sd.default.device
    if default_in is not None and default_in >= 0:
        return sd.query_devices(default_in)["hostapi"]
    return 0


def _list(kind: str) -> list[AudioDevice]:
    import sounddevice as sd

    try:
        hostapi = _default_hostapi()
        api = sd.query_hostapis(hostapi)
        default_index = api["default_input_device" if kind == "input" else "default_output_device"]
        channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
        result = []
        for index in api["devices"]:
            info = sd.query_devices(index)
            if info[channel_key] > 0:
                result.append(AudioDevice(index, info["name"], index == default_index))
        return result
    except Exception as exc:  # PortAudio unavailable or no devices
        log.error("Listing %s devices failed: %s", kind, exc)
        return []


def input_devices() -> list[AudioDevice]:
    return _list("input")


def output_devices() -> list[AudioDevice]:
    return _list("output")


def resolve(name: str, kind: str) -> int | None:
    """Device index for a stored name; None means "use the system default"."""
    if not name:
        return None
    for device in _list(kind):
        if device.name == name:
            return device.index
    log.warning("%s device %r not found; using the default", kind.capitalize(), name)
    return None
