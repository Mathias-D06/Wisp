"""Window tools (skill group "windows"): list, switch, minimise, maximise, restore, close."""

from __future__ import annotations

import time

from rapidfuzz import fuzz

from wisp.tools.base import Risk, Tool, ToolContext, ToolError, obj, string
from wisp.winapi import windows as win
from wisp.winapi.uia import ELEVATED_MESSAGE

MIN_SCORE = 60


def find_window(query: str | None) -> win.WindowInfo:
    candidates = win.list_windows()
    if not candidates:
        raise ToolError("There are no open windows.")
    if not query:
        fg = win.foreground_window()
        if fg and fg.hwnd in {w.hwnd for w in candidates}:
            return fg
        return candidates[0]
    scored = sorted(
        ((max(fuzz.WRatio(query, w.title), fuzz.WRatio(query, w.process) + 5), w)
         for w in candidates),
        key=lambda pair: pair[0], reverse=True,
    )
    if scored[0][0] < MIN_SCORE:
        raise ToolError(f"No open window matches '{query}'.")
    return scored[0][1]


def list_windows(ctx: ToolContext, args: dict) -> list[dict]:
    return [w.as_dict() for w in win.list_windows()][:30]


def switch_to_window(ctx: ToolContext, args: dict) -> dict:
    target = find_window(args["name"])
    if win.activate(target.hwnd):
        return {"switched_to": target.title}
    return {"switched_to": target.title,
            "note": "Windows didn't allow bringing it to the front; its taskbar button flashes."}


def window_action(ctx: ToolContext, args: dict) -> dict:
    target = find_window(args.get("name"))
    action = args["action"]
    if action == "minimize":
        win.minimize(target.hwnd)
    elif action == "maximize":
        win.maximize(target.hwnd)
    else:
        win.restore(target.hwnd)
    return {"window": target.title, "action": action}


def close_window(ctx: ToolContext, args: dict) -> dict:
    target = find_window(args["name"])
    if win.is_process_elevated(target.pid) and not win.self_elevated():
        raise ToolError(ELEVATED_MESSAGE)
    if not win.request_close(target.hwnd):
        raise ToolError(f"Windows refused to close '{target.title}'.")
    time.sleep(0.6)
    if win.is_window(target.hwnd):
        return {"window": target.title,
                "note": "Asked it to close; it is still open (it may be asking to save)."}
    return {"closed": target.title}


def tools() -> list[Tool]:
    name_param = string("Window title or app name; omit for the active window")
    return [
        Tool("list_windows", "List open windows (title, app, active, minimized).", obj(),
             list_windows, "windows", untrusted_output=True),
        Tool("switch_to_window", "Bring a window to the front.",
             obj({"name": string("Window title or app name")}, ["name"]), switch_to_window,
             "windows"),
        Tool("window_action", "Minimize, maximize or restore a window.",
             obj({"action": string("What to do", ["minimize", "maximize", "restore"]),
                  "name": name_param}, ["action"]),
             window_action, "windows"),
        Tool("close_window",
             "Close a window like clicking X (the app may ask to save). Needs confirmation.",
             obj({"name": string("Window title or app name")}, ["name"]), close_window,
             "windows", risk=Risk.CONFIRM, summary=lambda a: f"close the '{a.get('name')}' window"),
    ]
