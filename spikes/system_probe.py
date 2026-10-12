"""Spike (read-only): what the Island's system controls can see on this PC.

Media session (WinRT), radios (WinRT), Night Light registry blob (UNDOCUMENTED), theme values,
WMI brightness support, current wallpaper. Changes nothing.
Run: .venv\\Scripts\\python spikes\\system_probe.py
"""

import asyncio
import ctypes
import winreg

NIGHT_LIGHT_KEY = (r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount"
                   r"\Current\default$windows.data.bluelightreduction.bluelightreductionstate"
                   r"\windows.data.bluelightreduction.bluelightreductionstate")


async def media_and_radios() -> None:
    import winrt.windows.devices.radios as radios
    import winrt.windows.media.control as mc

    manager = await mc.GlobalSystemMediaTransportControlsSessionManager.request_async()
    session = manager.get_current_session()
    if session is None:
        print("media: no current session")
    else:
        props = await session.try_get_media_properties_async()
        timeline = session.get_timeline_properties()
        info = session.get_playback_info()
        print("media:", session.source_app_user_model_id, "|", props.title, "|", props.artist,
              "| status", info.playback_status, "| pos", timeline.position, "/", timeline.end_time)
    access = await radios.Radio.request_access_async()
    print("radio access:", access)
    for radio in await radios.Radio.get_radios_async():
        print("radio:", radio.kind, radio.name, radio.state)


def night_light() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NIGHT_LIGHT_KEY) as key:
            data, kind = winreg.QueryValueEx(key, "Data")
        print("night light blob:", len(data), "bytes, type", kind, "byte[18]=", hex(data[18]))
        print("  head:", data[:30].hex(" "))
    except OSError as exc:
        print("night light: unavailable", exc)


def theme() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
        for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            try:
                print("theme:", name, winreg.QueryValueEx(key, name)[0])
            except OSError:
                print("theme:", name, "missing")


def brightness() -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\WMI")
        levels = [m.CurrentBrightness for m in wmi.InstancesOf("WmiMonitorBrightness")]
        print("brightness:", levels)
    except Exception as exc:
        print("brightness: not supported here", type(exc).__name__)


def wallpaper() -> None:
    buffer = ctypes.create_unicode_buffer(520)
    ctypes.windll.user32.SystemParametersInfoW(0x0073, 520, buffer, 0)  # SPI_GETDESKWALLPAPER
    print("wallpaper:", buffer.value)


asyncio.run(media_and_radios())
night_light()
theme()
brightness()
wallpaper()
