"""Raw mouse and keyboard tools (skill group "input"): off by default, behind Settings → Safety
→ "Allow raw mouse and keyboard control" (F12.3).

These act blind — Wisp can't tell what a click at a coordinate will hit — so clicking and
risky keys always ask first and can never be auto-approved (DECISIONS.md D-034). Coordinates
are pixels of the most recent ``look_at_screen`` image and are mapped back to the screen.
Every tool refuses, with an explanation, when the secure desktop / lock screen is showing or the
target window runs as administrator while Wisp does not (UIPI); Wisp never works around either
(F12.6). It also refuses to send input into a full-screen window while an anti-cheat client is
running (D-035), because games may treat injected input as cheating. Input uses SendInput
(``winapi/input.py``).
"""

from __future__ import annotations

import time

from wisp.tools.base import Risk, Tool, ToolContext, ToolError, boolean, integer, obj, string
from wisp.winapi import input as winput
from wisp.winapi import processes, screen
from wisp.winapi import windows as win
from wisp.winapi.uia import ELEVATED_MESSAGE, SECURE_DESKTOP_MESSAGE

CAPTURE_MAX_AGE_S = 120
ANTI_CHEAT_MESSAGE = (
    "{products} is running and that window fills the screen, so it's probably a protected game. "
    "Wisp won't send keys or clicks to it: anti-cheat software can treat that as cheating. "
    "Please do it yourself.")

KEY_NAMES: dict[str, int] = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "apps": 0x5D, "menu": 0x5D,
    "volumeup": 0xAF, "volumedown": 0xAE, "volumemute": 0xAD,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
    **{chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
}
MODIFIERS = {"ctrl": winput.VK_CONTROL, "control": winput.VK_CONTROL, "shift": winput.VK_SHIFT,
             "alt": winput.VK_MENU, "win": winput.VK_LWIN, "windows": winput.VK_LWIN}
RISKY_KEYS = {"enter", "return", "delete", "del"}
RISKY_COMBOS = {frozenset({"alt", "f4"}), frozenset({"ctrl", "w"}), frozenset({"ctrl", "q"}),
                frozenset({"ctrl", "s"}), frozenset({"ctrl", "p"}), frozenset({"ctrl", "d"}),
                frozenset({"shift", "delete"}), frozenset({"ctrl", "enter"})}


def parse_keys(text: str) -> tuple[list[str], str]:
    """'Ctrl+Shift+T' → (['ctrl', 'shift'], 't'); raises ToolError for unknown names."""
    parts = [p.strip().lower() for p in (text or "").replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ToolError("No keys given.")
    *mods, key = parts
    aliases = {"control": "ctrl", "windows": "win", "escape": "esc", "return": "enter",
               "del": "delete"}
    mods = [aliases.get(m, m) for m in mods]
    key = aliases.get(key, key)
    unknown = [m for m in mods if m not in MODIFIERS] + ([] if key in KEY_NAMES else [key])
    if unknown:
        raise ToolError(f"Unknown key name(s): {', '.join(unknown)}.")
    return mods, key


def keys_risk(args: dict) -> Risk:
    try:
        mods, key = parse_keys(args.get("keys", ""))
    except ToolError:
        return Risk.CONFIRM
    names = frozenset(mods) | {key}
    if "win" in mods or key in RISKY_KEYS or any(c <= names for c in RISKY_COMBOS):
        return Risk.CONFIRM
    return Risk.SAFE


def text_risk(args: dict) -> Risk:
    text = args.get("text", "")
    return Risk.CONFIRM if "\n" in text or "\r" in text else Risk.SAFE


def is_fullscreen(bounds: tuple[int, int, int, int] | None,
                  monitor: tuple[int, int, int, int]) -> bool:
    if bounds is None:
        return False
    slack = 2
    return (bounds[0] <= monitor[0] + slack and bounds[1] <= monitor[1] + slack
            and bounds[2] >= monitor[2] - slack and bounds[3] >= monitor[3] - slack)


def _guard(target: win.WindowInfo | None) -> None:
    if not win.input_desktop_available():
        raise ToolError(SECURE_DESKTOP_MESSAGE)
    if target is None:
        return
    if win.is_process_elevated(target.pid) and not win.self_elevated():
        raise ToolError(ELEVATED_MESSAGE)
    products = processes.anti_cheat_running()
    if products:
        bounds = win.frame_bounds(target.hwnd)
        if bounds and is_fullscreen(bounds, screen.monitor_at((bounds[0] + bounds[2]) // 2,
                                                              (bounds[1] + bounds[3]) // 2)):
            raise ToolError(ANTI_CHEAT_MESSAGE.format(products=" and ".join(products)))


def _last_capture(ctx: ToolContext):
    entry = getattr(ctx.services, "last_capture", None)
    if entry is None or time.monotonic() - entry[1] > CAPTURE_MAX_AGE_S:
        raise ToolError("Call look_at_screen first; coordinates are pixels of that image.")
    return entry[0]


def mouse_click(ctx: ToolContext, args: dict) -> dict:
    shot = _last_capture(ctx)
    try:
        x, y = shot.to_screen(float(args["x"]), float(args["y"]))
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    target = win.window_at(x, y)
    _guard(target)
    winput.mouse_click(x, y, args.get("button", "left"), bool(args.get("double")))
    return {"clicked": [x, y], "window": target.title if target else None}


def press_keys(ctx: ToolContext, args: dict) -> dict:
    _guard(win.foreground_window())
    mods, key = parse_keys(args["keys"])
    winput.release_held_modifiers()
    winput.combo([MODIFIERS[m] for m in mods], KEY_NAMES[key])
    return {"pressed": "+".join([*mods, key])}


def type_text(ctx: ToolContext, args: dict) -> dict:
    text = args.get("text", "")
    if not text:
        raise ToolError("No text given.")
    if len(text) > 2000:
        raise ToolError("That's too much text to type at once (2000 characters max).")
    _guard(win.foreground_window())
    winput.release_held_modifiers()
    winput.type_text(text)
    return {"typed_chars": len(text)}


def mouse_scroll(ctx: ToolContext, args: dict) -> dict:
    _guard(win.foreground_window())
    clicks = max(-30, min(30, int(args["clicks"])))
    winput.mouse_wheel(clicks)
    return {"scrolled": clicks}


def tools() -> list[Tool]:
    common = {"risk": Risk.DISABLED, "enabled_by": "allow_raw_input"}
    return [
        Tool("mouse_click", "Click at a point of the latest look_at_screen image (asks first). "
             "Prefer click_element when the target has a name.",
             obj({"x": integer("X pixel in the screenshot"), "y": integer("Y pixel"),
                  "button": string("Mouse button", ["left", "right"]),
                  "double": boolean("Double-click")}, ["x", "y"]),
             mouse_click, "input", tier_when_enabled=Risk.CONFIRM, schedulable=False,
             summary=lambda a: f"click at ({a.get('x')}, {a.get('y')}) on the last screenshot",
             **common),
        Tool("press_keys", "Press a key or shortcut in the active window, e.g. 'ctrl+t', "
             "'alt+tab', 'f5'.",
             obj({"keys": string("Keys joined with +")}, ["keys"]),
             press_keys, "input", tier_when_enabled=Risk.SAFE, risk_fn=keys_risk,
             escalate_when_tainted=True, summary=lambda a: f"press {a.get('keys')}", **common),
        Tool("type_text", "Type text into the active window at the cursor (new lines ask "
             "first).",
             obj({"text": string("Text to type")}, ["text"]),
             type_text, "input", tier_when_enabled=Risk.SAFE, risk_fn=text_risk,
             escalate_when_tainted=True,
             summary=lambda a: f"type '{a.get('text', '')[:80]}'", **common),
        Tool("mouse_scroll", "Scroll the mouse wheel where the pointer is (positive = up).",
             obj({"clicks": integer("Wheel clicks, -30 to 30")}, ["clicks"]),
             mouse_scroll, "input", tier_when_enabled=Risk.SAFE, **common),
    ]
