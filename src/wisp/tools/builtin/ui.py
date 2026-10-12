"""UI Automation tools (skill group "ui"): list elements, click by name, type, scroll."""

from __future__ import annotations

import re
import time

from wisp.tools.base import Risk, Tool, ToolContext, ToolError, boolean, integer, obj, string
from wisp.winapi import windows as win
from wisp.winapi.uia import Uia, UiaLimit

RISKY_WORDS = [
    "send", "submit", "buy", "purchase", "pay", "order", "checkout", "check out", "delete",
    "remove", "erase", "format", "post", "publish", "tweet", "share", "transfer", "confirm",
    "install", "uninstall", "sign out", "log out", "unsubscribe", "accept", "agree", "allow",
    "ok", "yes", "run", "continue", "reply", "forward", "donate", "subscribe", "upload",
]
_RISKY = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in RISKY_WORDS) + r")(?!\w)",
                    re.IGNORECASE)


def is_risky_name(name: str) -> bool:
    return bool(_RISKY.search(name or ""))


def _uia_call(fn):
    try:
        return fn(Uia.for_thread())
    except UiaLimit as exc:
        raise ToolError(str(exc)) from exc


def list_ui_elements(ctx: ToolContext, args: dict) -> dict:
    def run(uia: Uia) -> dict:
        window = uia.target_window(args.get("window"))
        limit = max(5, min(args.get("limit", 60), 120))
        return {"window": window.title,
                "elements": uia.list_elements(window.hwnd, args.get("contains"), limit)}
    return _uia_call(run)


def click_element(ctx: ToolContext, args: dict) -> dict:
    def run(uia: Uia) -> dict:
        window = uia.target_window(args.get("window"))
        element = uia.find(window.hwnd, args["name"], args.get("control_type"))
        if not win.activate(window.hwnd):
            time.sleep(0.05)
        how = uia.click(element)
        return {"clicked": element.name, "type": element.control_type, "how": how,
                "window": window.title}
    return _uia_call(run)


def type_into_field(ctx: ToolContext, args: dict) -> dict:
    def run(uia: Uia) -> dict:
        window = uia.target_window(args.get("window"))
        if args.get("field"):
            element = uia.find(window.hwnd, args["field"], editable=True)
        else:
            element = uia.first_editable(window.hwnd)
        win.activate(window.hwnd)
        how = uia.type_into(element, args["text"])
        if args.get("submit"):
            element.raw.SetFocus()
            time.sleep(0.05)
            uia.press_enter()
        return {"field": element.name or element.control_type, "how": how,
                "submitted": bool(args.get("submit"))}
    return _uia_call(run)


def scroll(ctx: ToolContext, args: dict) -> dict:
    def run(uia: Uia) -> dict:
        window = uia.target_window(args.get("window"))
        amount = max(1, min(args.get("amount", 1), 10))
        how = uia.scroll(window.hwnd, args["direction"], amount)
        return {"window": window.title, "direction": args["direction"], "how": how}
    return _uia_call(run)


def _click_risk(args: dict) -> Risk:
    return Risk.CONFIRM if is_risky_name(args.get("name", "")) else Risk.SAFE


def _type_risk(args: dict) -> Risk:
    return Risk.CONFIRM if args.get("submit") else Risk.SAFE


def tools() -> list[Tool]:
    window = string("Window title or app; omit for the active window")
    return [
        Tool("list_ui_elements", "List buttons, fields and other controls in a window.",
             obj({"window": window, "contains": string("Only names containing this text"),
                  "limit": integer("Max elements")}),
             list_ui_elements, "ui", untrusted_output=True, schedulable=False),
        Tool("click_element", "Click a button, link, tab or menu item by its visible name.",
             obj({"name": string("Visible name of the control"),
                  "control_type": string("Optional type, e.g. Button, TabItem, Hyperlink"),
                  "window": window}, ["name"]),
             click_element, "ui", risk_fn=_click_risk, escalate_when_tainted=True,
             summary=lambda a: f"click '{a.get('name')}'"),
        Tool("type_into_field", "Type text into a field (the focused one if not named). "
             "submit=true presses Enter afterwards.",
             obj({"text": string("Text to type"), "field": string("Field name, optional"),
                  "window": window, "submit": boolean("Press Enter after typing")}, ["text"]),
             type_into_field, "ui", risk_fn=_type_risk, escalate_when_tainted=True,
             summary=lambda a: f"type '{a.get('text', '')[:60]}'"
             + (" and press Enter" if a.get("submit") else "")),
        Tool("scroll", "Scroll a window up, down, left or right.",
             obj({"direction": string("Direction", ["up", "down", "left", "right"]),
                  "amount": integer("How many pages (1-10)"), "window": window},
                 ["direction"]),
             scroll, "ui"),
    ]
