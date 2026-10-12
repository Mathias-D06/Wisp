"""Wi-Fi and Bluetooth on/off via WinRT Windows.Devices.Radios (documented).

Source: learn.microsoft.com/uwp/api/windows.devices.radios.radio — RequestAccessAsync before
control, GetRadiosAsync, SetStateAsync; hardware switches or policy can deny changes.
Coroutines run on the core asyncio loop (proven by spikes/winrt_in_loop_thread.py).
"""

from __future__ import annotations

KINDS = {"wifi": "WI_FI", "bluetooth": "BLUETOOTH"}


async def states() -> dict[str, bool | None]:
    import winrt.windows.devices.radios as radios

    result: dict[str, bool | None] = {name: None for name in KINDS}
    for radio in await radios.Radio.get_radios_async():
        for name, kind in KINDS.items():
            if radio.kind == getattr(radios.RadioKind, kind):
                result[name] = radio.state == radios.RadioState.ON
    return result


async def set_state(name: str, enabled: bool) -> str:
    """Returns "ok", "denied" or "missing"."""
    import winrt.windows.devices.radios as radios

    access = await radios.Radio.request_access_async()
    if access != radios.RadioAccessStatus.ALLOWED:
        return "denied"
    kind = getattr(radios.RadioKind, KINDS[name])
    found = False
    for radio in await radios.Radio.get_radios_async():
        if radio.kind == kind:
            found = True
            target = radios.RadioState.ON if enabled else radios.RadioState.OFF
            status = await radio.set_state_async(target)
            if status != radios.RadioAccessStatus.ALLOWED:
                return "denied"
    return "ok" if found else "missing"
