"""Spike: UI Automation through comtypes (documented IUIAutomation COM API). Read-only.

Generates the UIAutomationClient wrapper from UIAutomationCore.dll, prints the constants Wisp
uses, and lists named control elements of the taskbar window from a worker thread in the
multithreaded apartment (how Wisp's tool workers run). Clicks nothing.
Run: .venv\\Scripts\\python spikes\\uia_probe.py
"""

import threading
import time

import comtypes.client
import pythoncom
import win32gui

comtypes.client.GetModule("UIAutomationCore.dll")
from comtypes.gen import UIAutomationClient as UIA  # noqa: E402

NAMES = ("UIA_InvokePatternId", "UIA_ValuePatternId", "UIA_ScrollPatternId",
         "UIA_TogglePatternId", "UIA_SelectionItemPatternId", "UIA_ExpandCollapsePatternId",
         "UIA_LegacyIAccessiblePatternId", "UIA_NamePropertyId", "UIA_IsOffscreenPropertyId",
         "UIA_IsControlElementPropertyId", "UIA_ButtonControlTypeId", "UIA_EditControlTypeId",
         "TreeScope_Descendants", "ScrollAmount_LargeIncrement")


def probe() -> None:
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    for name in NAMES:
        print(f"{name} = {getattr(UIA, name, 'MISSING')}")
    automation = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    root = automation.ElementFromHandle(win32gui.FindWindow("Shell_TrayWnd", None))
    condition = automation.CreateAndCondition(
        automation.CreatePropertyCondition(UIA.UIA_IsControlElementPropertyId, True),
        automation.CreatePropertyCondition(UIA.UIA_IsOffscreenPropertyId, False),
    )
    started = time.perf_counter()
    found = root.FindAll(UIA.TreeScope_Descendants, condition)
    print(f"taskbar: {found.Length} control elements in {time.perf_counter() - started:.2f}s")
    for index in range(min(found.Length, 10)):
        element = found.GetElement(index)
        rect = element.CurrentBoundingRectangle
        invoke = element.GetCurrentPattern(UIA.UIA_InvokePatternId)
        print(f"  {element.CurrentControlType} {element.CurrentLocalizedControlType!r:14} "
              f"{element.CurrentName!r:38} invoke={bool(invoke)} "
              f"rect=({rect.left},{rect.top},{rect.right},{rect.bottom})")


worker = threading.Thread(target=probe)
worker.start()
worker.join()
