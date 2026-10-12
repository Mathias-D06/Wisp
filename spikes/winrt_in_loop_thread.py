"""Spike: WinRT media/radio calls awaited on Wisp's core asyncio thread while the main thread is
a Qt GUI thread (STA, comtypes imported) — the exact threading the app uses. Read-only.

Run: .venv\\Scripts\\python spikes\\winrt_in_loop_thread.py
"""

import sys

import comtypes.client  # noqa: F401  (as in the app: COM initialised on the main thread)
from PySide6.QtWidgets import QApplication

from wisp.loop import LoopThread


async def probe() -> list[str]:
    import winrt.windows.devices.radios as radios
    import winrt.windows.media.control as mc

    lines = []
    manager = await mc.GlobalSystemMediaTransportControlsSessionManager.request_async()
    session = manager.get_current_session()
    lines.append(f"media session: {session.source_app_user_model_id if session else None}")
    lines.append(f"radio access: {await radios.Radio.request_access_async()}")
    for radio in await radios.Radio.get_radios_async():
        lines.append(f"radio {radio.name}: {radio.state}")
    return lines


app = QApplication(sys.argv)
loop = LoopThread()
loop.start()
for line in loop.submit(probe()).result(20):
    print(line)
loop.stop()
