"""Windows UI Automation client via comtypes (documented IUIAutomation COM API).

Proven by ``spikes/uia_probe.py``: the wrapper is generated from UIAutomationCore.dll and works
from MTA worker threads. COM objects are per-thread, so each thread gets its own client.
Windows' UIPI blocks automation of windows that run elevated when Wisp is not; the secure desktop
(UAC prompts, lock screen) is not reachable at all. Both cases raise a clear UiaLimit.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

# comtypes initialises COM (STA) in the thread that first imports it, and that raises in MTA
# worker threads. Importing it here, at app start-up on the main thread, avoids that.
import comtypes.client
from rapidfuzz import fuzz

from wisp.winapi import input as winput
from wisp.winapi import windows

log = logging.getLogger(__name__)

MAX_ELEMENTS = 400
_local = threading.local()


class UiaLimit(RuntimeError):
    """A Windows security boundary or missing UI element, explained in plain words."""


ELEVATED_MESSAGE = (
    "That window belongs to an app running as administrator. Windows blocks other apps from "
    "controlling it (UIPI) and Wisp will not try to bypass that. Use it directly instead."
)
SECURE_DESKTOP_MESSAGE = (
    "Windows is showing a secure screen (lock screen or an administrator/UAC prompt). Apps "
    "cannot see or control it, by design. Please handle it yourself."
)


def _module():
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient

    return UIAutomationClient


@dataclass
class Element:
    name: str
    control_type: str
    enabled: bool
    rect: tuple[int, int, int, int]
    raw: Any = None

    def as_dict(self) -> dict:
        data = {"name": self.name, "type": self.control_type}
        if not self.enabled:
            data["enabled"] = False
        return data


class Uia:
    def __init__(self) -> None:
        self.UIA = _module()
        self.auto = comtypes.client.CreateObject(self.UIA.CUIAutomation,
                                                 interface=self.UIA.IUIAutomation)
        self.type_names = {
            getattr(self.UIA, attr): attr[4:-len("ControlTypeId")]
            for attr in dir(self.UIA)
            if attr.startswith("UIA_") and attr.endswith("ControlTypeId")
        }

    @classmethod
    def for_thread(cls) -> Uia:
        client = getattr(_local, "client", None)
        if client is None:
            client = cls()
            _local.client = client
        return client

    # ----- target window ---------------------------------------------------------------------
    @staticmethod
    def target_window(query: str | None) -> windows.WindowInfo:
        if not windows.input_desktop_available():
            raise UiaLimit(SECURE_DESKTOP_MESSAGE)
        candidates = windows.list_windows()
        if query:
            scored = sorted(
                ((max(fuzz.WRatio(query, w.title), fuzz.WRatio(query, w.process)), w)
                 for w in candidates),
                key=lambda pair: pair[0], reverse=True,
            )
            if not scored or scored[0][0] < 60:
                raise UiaLimit(f"No open window matches '{query}'.")
            target = scored[0][1]
        else:
            fg = windows.foreground_window()
            others = {w.hwnd for w in candidates}
            target = fg if fg and fg.hwnd in others else (candidates[0] if candidates else None)
            if target is None:
                raise UiaLimit("There is no open window to work with.")
        if windows.is_process_elevated(target.pid) and not windows.self_elevated():
            raise UiaLimit(ELEVATED_MESSAGE)
        return target

    # ----- elements --------------------------------------------------------------------------
    def _elements(self, hwnd: int) -> list[Element]:
        root = self.auto.ElementFromHandle(hwnd)
        condition = self.auto.CreateAndCondition(
            self.auto.CreatePropertyCondition(self.UIA.UIA_IsControlElementPropertyId, True),
            self.auto.CreatePropertyCondition(self.UIA.UIA_IsOffscreenPropertyId, False),
        )
        found = root.FindAll(self.UIA.TreeScope_Descendants, condition)
        result = []
        for index in range(min(found.Length, MAX_ELEMENTS)):
            raw = found.GetElement(index)
            try:
                name = (raw.CurrentName or "").strip()
                kind = self.type_names.get(raw.CurrentControlType, "Control")
                rect = raw.CurrentBoundingRectangle
                if not name and kind not in ("Edit", "Document", "ComboBox"):
                    continue
                result.append(Element(name[:120], kind, bool(raw.CurrentIsEnabled),
                                      (rect.left, rect.top, rect.right, rect.bottom), raw))
            except Exception as exc:  # element vanished while reading
                log.debug("Skipping element: %s", exc)
        return result

    def list_elements(self, hwnd: int, contains: str | None = None, limit: int = 60) -> list[dict]:
        seen = set()
        rows = []
        for element in self._elements(hwnd):
            if contains and contains.lower() not in element.name.lower():
                continue
            key = (element.name, element.control_type)
            if key in seen:
                continue
            seen.add(key)
            rows.append(element.as_dict())
            if len(rows) >= limit:
                break
        return rows

    def find(self, hwnd: int, name: str, control_type: str | None = None,
             editable: bool = False) -> Element:
        best: tuple[float, Element] | None = None
        for element in self._elements(hwnd):
            if control_type and element.control_type.lower() != control_type.lower():
                continue
            if editable and element.control_type not in ("Edit", "Document", "ComboBox"):
                continue
            score = fuzz.WRatio(name, element.name) if element.name else 0
            if element.name.lower() == name.lower():
                score += 20
            if best is None or score > best[0]:
                best = (score, element)
        if best is None or best[0] < 70:
            raise UiaLimit(f"I couldn't find '{name}' in that window. Ask me to list the "
                           "elements to see what's there.")
        return best[1]

    def first_editable(self, hwnd: int) -> Element:
        focused = self.auto.GetFocusedElement()
        if focused is not None:
            try:
                kind = self.type_names.get(focused.CurrentControlType, "")
                if kind in ("Edit", "Document", "ComboBox"):
                    rect = focused.CurrentBoundingRectangle
                    return Element(focused.CurrentName or "", kind, True,
                                   (rect.left, rect.top, rect.right, rect.bottom), focused)
            except Exception as exc:
                log.debug("Focused element unreadable: %s", exc)
        for element in self._elements(hwnd):
            if element.control_type in ("Edit", "Document") and element.enabled:
                return element
        raise UiaLimit("There is no text field in that window.")

    # ----- actions ---------------------------------------------------------------------------
    def _pattern(self, element: Element, pattern_id: int, interface: Any):
        unknown = element.raw.GetCurrentPattern(pattern_id)
        return unknown.QueryInterface(interface) if unknown else None

    def click(self, element: Element) -> str:
        if not element.enabled:
            raise UiaLimit(f"'{element.name}' is disabled right now.")
        UIA = self.UIA
        invoke = self._pattern(element, UIA.UIA_InvokePatternId, UIA.IUIAutomationInvokePattern)
        if invoke:
            invoke.Invoke()
            return "invoked"
        toggle = self._pattern(element, UIA.UIA_TogglePatternId, UIA.IUIAutomationTogglePattern)
        if toggle:
            toggle.Toggle()
            return "toggled"
        select = self._pattern(element, UIA.UIA_SelectionItemPatternId,
                               UIA.IUIAutomationSelectionItemPattern)
        if select:
            select.Select()
            return "selected"
        expand = self._pattern(element, UIA.UIA_ExpandCollapsePatternId,
                               UIA.IUIAutomationExpandCollapsePattern)
        if expand:
            expand.Expand()
            return "expanded"
        legacy = self._pattern(element, UIA.UIA_LegacyIAccessiblePatternId,
                               UIA.IUIAutomationLegacyIAccessiblePattern)
        if legacy:
            legacy.DoDefaultAction()
            return "default action"
        left, top, right, bottom = element.rect
        if right > left and bottom > top:
            winput.mouse_click((left + right) // 2, (top + bottom) // 2)
            return "clicked at the element's centre"
        raise UiaLimit(f"'{element.name}' can't be clicked.")

    def type_into(self, element: Element, text: str) -> str:
        UIA = self.UIA
        value = self._pattern(element, UIA.UIA_ValuePatternId, UIA.IUIAutomationValuePattern)
        if value is not None and not value.CurrentIsReadOnly:
            try:
                value.SetValue(text)
                return "set"
            except Exception as exc:  # some controls refuse SetValue; fall back to typing
                log.debug("SetValue failed: %s", exc)
        element.raw.SetFocus()
        time.sleep(0.05)
        winput.type_text(text)
        return "typed"

    def press_enter(self) -> None:
        winput.tap(0x0D)

    def scroll(self, hwnd: int, direction: str, amount: int) -> str:
        UIA = self.UIA
        root = self.auto.ElementFromHandle(hwnd)
        condition = self.auto.CreatePropertyCondition(
            UIA.UIA_IsScrollPatternAvailablePropertyId, True)
        target = root.FindFirst(UIA.TreeScope_Subtree, condition)
        if target is not None:
            scroll = target.GetCurrentPattern(UIA.UIA_ScrollPatternId)
            if scroll:
                pattern = scroll.QueryInterface(UIA.IUIAutomationScrollPattern)
                step = UIA.ScrollAmount_LargeIncrement
                back = UIA.ScrollAmount_LargeDecrement
                none = UIA.ScrollAmount_NoAmount
                horizontal = {"left": back, "right": step}.get(direction, none)
                vertical = {"up": back, "down": step}.get(direction, none)
                for _ in range(max(1, amount)):
                    pattern.Scroll(horizontal, vertical)
                return "scrolled"
        windows.activate(hwnd)
        clicks = amount * 3 * (1 if direction == "up" else -1)
        if direction in ("up", "down"):
            winput.mouse_wheel(clicks)
            return "scrolled with the mouse wheel"
        raise UiaLimit("That window can't scroll sideways.")
