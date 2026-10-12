"""Spike: confirm the IShellItemImageFactory IID is registered on this system and extract a
Store-app and a desktop-app icon via wisp.winapi.shell_icons. Writes PNGs to spikes/out.

Run: .venv\\Scripts\\python spikes\\shell_icon_probe.py
"""

import threading
import winreg
from pathlib import Path

import comtypes.client  # noqa: F401  (main-thread COM init, as in the app)
import pythoncom

from wisp.system.app_index import AppIndex
from wisp.winapi.shell_icons import IID_IShellItemImageFactory, icon_png, parsing_name

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"Interface\\{IID_IShellItemImageFactory}") as key:
    print("registered interface name:", winreg.QueryValue(key, ""))


def work() -> None:
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    apps = AppIndex._apps_folder()
    store = next((a for a in apps if "!" in a[1]), None)
    desktop = next((a for a in apps if a[2] == "path" and a[1].lower().endswith(".exe")), None)
    for label, app in (("store", store), ("desktop", desktop)):
        if app is None:
            print(label, "none found")
            continue
        png = icon_png(parsing_name(app[1], app[2]), 48)
        print(label, app[0], "->", len(png) if png else None, "bytes")
        if png:
            (OUT / f"icon_{label}.png").write_bytes(png)


thread = threading.Thread(target=work)
thread.start()
thread.join()
