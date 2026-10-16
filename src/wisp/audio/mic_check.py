"""Telling a microphone that delivers nothing apart from a quiet room (D-055).

A working microphone always carries some noise: a quiet room sits around −60 dBFS, dozens of
int16 steps. A stream whose every sample stays within ``SILENT_PEAK`` steps of zero (about
−78 dBFS) is not hearing the room at all. Windows does that when its microphone privacy
switches block the app, when the mic is muted by a key or a switch on the laptop, or when the
input chosen is not the one in use. Wisp then says which Windows setting to check instead of
sending silence (which Gemini turns into invented words, D-039).

The privacy switches are read, never written, from the registry values behind Settings →
Privacy & security → Microphone (UNDOCUMENTED by Microsoft; mapping from elevenforum.com's
tutorial, checked on this PC): ``ConsentStore\\microphone`` ``Value`` under HKLM ("Microphone
access", for the whole device) and HKCU ("Let apps access your microphone"), and
``ConsentStore\\microphone\\NonPackaged`` ``Value`` under HKCU ("Let desktop apps access your
microphone"), each "Allow" or "Deny". Wisp is a desktop app, so all three must be on.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from wisp.audio import INPUT_RATE

log = logging.getLogger(__name__)

SILENT_PEAK = 4  # int16 steps; a working mic's noise is far above this
MIN_SILENT_S = 0.3  # judge at least this much audio
PRIVACY_PAGE = "Windows Settings → Privacy & security → Microphone"
_CONSENT = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore" \
           r"\microphone"
SWITCHES = (  # (hive, subkey, the switch's name in Settings)
    ("HKLM", _CONSENT, "Microphone access"),
    ("HKCU", _CONSENT, "Let apps access your microphone"),
    ("HKCU", _CONSENT + r"\NonPackaged", "Let desktop apps access your microphone"),
)


def is_dead_silence(pcm: bytes, min_seconds: float = MIN_SILENT_S) -> bool:
    """True if ``pcm`` (16 kHz mono int16) is long enough to judge and never leaves the
    bottom ``SILENT_PEAK`` steps: the microphone isn't delivering sound at all."""
    usable = len(pcm) - len(pcm) % 2
    if usable < INPUT_RATE * 2 * min_seconds:
        return False
    samples = np.frombuffer(pcm[:usable], dtype="<i2")
    return int(np.max(np.abs(samples.astype(np.int32)))) <= SILENT_PEAK


def channels_silent(levels_dbfs: list[float], threshold_dbfs: float = -85.0) -> bool:
    """Every device channel below ``threshold_dbfs`` (the 1 s level check)."""
    return bool(levels_dbfs) and all(level <= threshold_dbfs for level in levels_dbfs)


def _read_value(hive: str, subkey: str) -> str | None:
    import winreg

    root = winreg.HKEY_LOCAL_MACHINE if hive == "HKLM" else winreg.HKEY_CURRENT_USER
    try:
        with winreg.OpenKey(root, subkey) as key:
            value, _kind = winreg.QueryValueEx(key, "Value")
    except OSError:
        return None  # never set: Windows' default (on)
    return str(value)


def privacy_states(read: Callable[[str, str], str | None] | None = None,
                   ) -> list[tuple[str, str | None]]:
    """(switch name, "Allow" / "Deny" / None when never set) for each switch, in Settings'
    order. ``read`` replaces the registry for tests."""
    reader = read or _read_value
    states = []
    for hive, subkey, name in SWITCHES:
        try:
            states.append((name, reader(hive, subkey)))
        except Exception as exc:  # not Windows, or the read failed: unknown, not "off"
            log.debug("Reading %s failed: %s", name, exc)
            states.append((name, None))
    return states


def blocked_switches(states: list[tuple[str, str | None]]) -> list[str]:
    return [name for name, value in states if (value or "").lower() == "deny"]


def silence_notice(device: str, states: list[tuple[str, str | None]]) -> str:
    """What to tell the user when the microphone delivers only silence."""
    mic = f"the microphone “{device}”" if device else "the microphone"
    blocked = blocked_switches(states)
    if blocked:
        switches = " and ".join(f"“{name}”" for name in blocked)
        return (f"Wisp got only silence from {mic}: Windows is blocking it. Turn on {switches} "
                f"in {PRIVACY_PAGE}, then try again.")
    return (f"Wisp got only silence from {mic}, so nothing was sent. Check that “Let desktop "
            f"apps access your microphone” is on in {PRIVACY_PAGE}; that the mic isn't muted "
            "(a mute key or switch on the laptop); and that it is the microphone you use "
            "(Windows Settings → System → Sound → Input, or Wisp's Settings → Hotkeys and "
            "audio). Test microphone in Wisp's settings shows what it hears.")


def describe_states(states: list[tuple[str, str | None]]) -> str:
    """For the log: e.g. "Microphone access=Allow, … desktop apps …=Deny"."""
    return ", ".join(f"{name}={value or 'not set'}" for name, value in states)


def notice_if_silent(pcm: bytes, device: str,
                     states: Callable[[], list[tuple[str, str | None]]] = privacy_states,
                     ) -> str | None:
    """The notice for ``pcm`` from ``device`` if it is dead silence (logged), else None."""
    if not is_dead_silence(pcm):
        return None
    found = states()
    log.warning("The microphone %r delivered only silence (%.1f s); Windows microphone "
                "privacy: %s", device, len(pcm) / (INPUT_RATE * 2), describe_states(found))
    return silence_notice(device, found)
