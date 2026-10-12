"""Spike: enumerate the Apps folder (desktop + Store apps) through the documented Shell.Application
object and check that Folder.ParseName(AUMID) finds an item again. Launches nothing.

Source: https://learn.microsoft.com/en-us/windows/configuration/store/find-aumid
Run: .venv\\Scripts\\python spikes\\apps_folder.py
"""

import time

import pythoncom
import win32com.client

APPS_FOLDER = "shell:::{4234d49b-0245-4df3-b780-3893943456e1}"

pythoncom.CoInitialize()
started = time.perf_counter()
shell = win32com.client.Dispatch("Shell.Application")
folder = shell.NameSpace(APPS_FOLDER)
items = [(item.Name, item.Path) for item in folder.Items()]
elapsed = time.perf_counter() - started
print(f"{len(items)} apps in {elapsed:.2f}s")
for name, path in items[:8]:
    print(f"  {name!r:40} {path}")
store = [p for _, p in items if "!" in p]
print("store-style AUMIDs:", len(store))
if items:
    name, path = items[0]
    again = folder.ParseName(path)
    print("ParseName round trip:", bool(again), again.Name if again else None)
    verbs = [v.Name for v in again.Verbs()] if again else []
    print("verbs:", verbs[:6])
