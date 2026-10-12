"""Quick system controls for the Island's Controls tab and the "system" voice tools.

Documented: volume/mute via Core Audio IAudioEndpointVolume (pycaw); brightness via WMI
WmiMonitorBrightness(Methods) in root\\WMI (laptop panels only); Wi-Fi/Bluetooth via WinRT
Windows.Devices.Radios (see media.py's loop for awaiting).
UNDOCUMENTED (DECISIONS.md D-030): Night Light registry blob, dark-mode registry values written
by apps, default-output switching via the IPolicyConfig COM interface. Each is isolated here and
fails with ControlUnavailable so the UI can offer the matching ms-settings: page instead.
All functions block; call them from COM-initialised worker threads, not the Qt thread.
"""

from __future__ import annotations

import ctypes
import logging
import time
import winreg
from dataclasses import dataclass

log = logging.getLogger(__name__)

SETTINGS_PAGES = {
    "night_light": "ms-settings:nightlight",
    "dark_mode": "ms-settings:colors",
    "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth",
    "output": "ms-settings:sound",
    "brightness": "ms-settings:display",
}


class ControlUnavailable(RuntimeError):
    """The control can't be changed here; ``page`` is the Settings page to open instead."""

    def __init__(self, message: str, page: str):
        super().__init__(message)
        self.page = page


# ----- volume (documented Core Audio) ------------------------------------------------------------
def _endpoint_volume():
    from pycaw.pycaw import AudioUtilities

    speakers = AudioUtilities.GetSpeakers()
    if speakers is None:
        raise ControlUnavailable("No audio output device.", SETTINGS_PAGES["output"])
    return speakers.EndpointVolume


def volume() -> tuple[int, bool]:
    endpoint = _endpoint_volume()
    return round(endpoint.GetMasterVolumeLevelScalar() * 100), bool(endpoint.GetMute())


def set_volume(level: int) -> int:
    level = max(0, min(100, int(level)))
    endpoint = _endpoint_volume()
    endpoint.SetMasterVolumeLevelScalar(level / 100, None)
    if level > 0 and endpoint.GetMute():
        endpoint.SetMute(0, None)
    return level


def set_mute(muted: bool) -> None:
    _endpoint_volume().SetMute(int(muted), None)


# ----- output devices ----------------------------------------------------------------------------
@dataclass(frozen=True)
class OutputDevice:
    id: str
    name: str
    is_default: bool


def output_devices() -> list[OutputDevice]:
    from pycaw.constants import DEVICE_STATE, EDataFlow, ERole
    from pycaw.pycaw import AudioUtilities

    enumerator = AudioUtilities.GetDeviceEnumerator()
    default = enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eMultimedia.value)
    default_id = default.GetId() if default else ""
    devices = AudioUtilities.GetAllDevices(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
    return [OutputDevice(d.id, d.FriendlyName or d.id, d.id == default_id) for d in devices]


def set_default_output(device_id: str) -> None:
    """UNDOCUMENTED: IPolicyConfig (pycaw.AudioUtilities.SetDefaultDevice)."""
    from pycaw.constants import ERole
    from pycaw.pycaw import AudioUtilities

    try:
        AudioUtilities.SetDefaultDevice(device_id, [ERole.eConsole, ERole.eMultimedia,
                                                    ERole.eCommunications])
    except OSError as exc:
        raise ControlUnavailable(f"Windows refused to switch the output device ({exc}).",
                                 SETTINGS_PAGES["output"]) from exc


# ----- brightness (documented WMI) ---------------------------------------------------------------
def _wmi():
    import win32com.client

    return win32com.client.GetObject("winmgmts:\\\\.\\root\\WMI")


def brightness() -> int | None:
    """Current brightness of the built-in panel, or None on PCs without one."""
    try:
        levels = [int(m.CurrentBrightness) for m in _wmi().InstancesOf("WmiMonitorBrightness")]
    except Exception:
        return None
    return levels[0] if levels else None


def set_brightness(level: int) -> int:
    level = max(0, min(100, int(level)))
    try:
        methods = list(_wmi().InstancesOf("WmiMonitorBrightnessMethods"))
    except Exception:
        methods = []
    if not methods:
        raise ControlUnavailable("This display's brightness can't be set from Windows "
                                 "(external monitors use their own buttons).",
                                 SETTINGS_PAGES["brightness"])
    for instance in methods:
        # SWbemObject.ExecMethod_ with named in-parameters (documented scripting pattern).
        params = instance.Methods_("WmiSetBrightness").InParameters.SpawnInstance_()
        params.Properties_.Item("Timeout").Value = 1
        params.Properties_.Item("Brightness").Value = level
        instance.ExecMethod_("WmiSetBrightness", params)
    return level


# ----- dark mode (UNDOCUMENTED write) ------------------------------------------------------------
PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002


def dark_mode() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def set_dark_mode(enabled: bool) -> None:
    value = 0 if enabled else 1
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, value)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, value)
    except OSError as exc:
        raise ControlUnavailable(f"Couldn't change the theme ({exc}).",
                                 SETTINGS_PAGES["dark_mode"]) from exc
    result = ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0,
                                             "ImmersiveColorSet", SMTO_ABORTIFHUNG, 2000,
                                             ctypes.byref(result))


# ----- Night Light (UNDOCUMENTED blob) -----------------------------------------------------------
NIGHT_LIGHT_KEY = (r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount"
                   r"\Current\default$windows.data.bluelightreduction.bluelightreductionstate"
                   r"\windows.data.bluelightreduction.bluelightreductionstate")
_ON, _OFF = 0x15, 0x13
_ON_MARKER = b"\x10\x00"


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _decode_varint(data: bytes) -> int:
    value = 0
    for shift, byte in enumerate(data):
        value |= (byte & 0x7F) << (7 * shift)
        if not byte & 0x80:
            break
    return value


def parse_night_light(data: bytes) -> bool:
    """Night Light state from the CloudStore blob; raises ValueError if the layout is unknown."""
    if len(data) < 25 or data[:2] != b"CB" or data[18] not in (_ON, _OFF):
        raise ValueError("unknown Night Light data layout")
    return data[18] == _ON


def toggle_night_light_blob(data: bytes, enabled: bool, now: int | None = None) -> bytes:
    """Rewrite the blob for the requested state and refresh its change timestamp (bytes 10-14,
    a little-endian base-128 varint of Unix time; observed on this PC's blob)."""
    current = parse_night_light(data)
    blob = bytearray(data)
    stamp = _encode_varint(int(now if now is not None else time.time()))
    if len(stamp) == 5 and _decode_varint(blob[10:15]) > 0:
        blob[10:15] = stamp
    if enabled == current:
        return bytes(blob)
    if enabled:
        blob[18] = _ON
        blob[23:23] = _ON_MARKER
    else:
        blob[18] = _OFF
        if blob[23:25] == _ON_MARKER:
            del blob[23:25]
    return bytes(blob)


def night_light() -> bool | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NIGHT_LIGHT_KEY) as key:
            data, _kind = winreg.QueryValueEx(key, "Data")
        return parse_night_light(bytes(data))
    except (OSError, ValueError):
        return None


def set_night_light(enabled: bool) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NIGHT_LIGHT_KEY, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
            data, kind = winreg.QueryValueEx(key, "Data")
            winreg.SetValueEx(key, "Data", 0, kind,
                              toggle_night_light_blob(bytes(data), enabled))
    except (OSError, ValueError) as exc:
        raise ControlUnavailable("Night Light can't be switched directly on this PC.",
                                 SETTINGS_PAGES["night_light"]) from exc
