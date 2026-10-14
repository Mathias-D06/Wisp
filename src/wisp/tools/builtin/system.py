"""System, media, power and clipboard tools (skill groups "system", "media", "power",
"clipboard"). Few tools with an action argument keep the declaration tokens low."""

from __future__ import annotations

from rapidfuzz import fuzz

from wisp.system import controls, power, radios, wallpaper
from wisp.tools.base import Risk, Tool, ToolContext, ToolError, boolean, integer, obj, string


# ----- system ------------------------------------------------------------------------------------
def volume_tool(ctx: ToolContext, args: dict) -> dict:
    action = args["action"]
    level, muted = controls.volume()
    if action == "get":
        return {"volume": level, "muted": muted}
    if action == "mute":
        controls.set_mute(True)
        return {"muted": True}
    if action == "unmute":
        controls.set_mute(False)
        return {"muted": False, "volume": level}
    step = args.get("level", 10)
    target = {"set": step, "up": level + step, "down": level - step}[action]
    return {"volume": controls.set_volume(target)}


def brightness_tool(ctx: ToolContext, args: dict) -> dict:
    current = controls.brightness()
    if current is None:
        raise ToolError("This PC's display brightness can't be changed from Windows "
                        "(external monitors use their own buttons).")
    action = args["action"]
    if action == "get":
        return {"brightness": current}
    step = args.get("level", 10)
    target = {"set": step, "up": current + step, "down": current - step}[action]
    try:
        return {"brightness": controls.set_brightness(target)}
    except controls.ControlUnavailable as exc:
        raise ToolError(str(exc)) from exc


async def toggle_tool(ctx: ToolContext, args: dict) -> dict:
    setting, enabled = args["setting"], args["on"]
    try:
        if setting in ("wifi", "bluetooth"):
            outcome = await radios.set_state(setting, enabled)
            if outcome == "denied":
                raise ToolError(f"Windows didn't allow changing {setting} (a hardware switch or "
                                "policy may block it).")
            if outcome == "missing":
                raise ToolError(f"This PC has no {setting} radio.")
        elif setting == "dark_mode":
            controls.set_dark_mode(enabled)
        else:
            controls.set_night_light(enabled)
    except controls.ControlUnavailable as exc:
        raise ToolError(f"{exc} I can open {exc.page} for you instead.") from exc
    return {setting: "on" if enabled else "off"}


def output_device_tool(ctx: ToolContext, args: dict) -> dict:
    devices = controls.output_devices()
    if not args.get("name"):
        return {"devices": [d.name for d in devices],
                "default": next((d.name for d in devices if d.is_default), None)}
    scored = sorted(((fuzz.WRatio(args["name"], d.name), d) for d in devices),
                    key=lambda pair: pair[0], reverse=True)
    if not scored or scored[0][0] < 60:
        raise ToolError(f"No output device matches '{args['name']}'. Devices: "
                        + ", ".join(d.name for d in devices))
    device = scored[0][1]
    try:
        controls.set_default_output(device.id)
    except controls.ControlUnavailable as exc:
        raise ToolError(str(exc)) from exc
    return {"default_output": device.name}


def _toggle_risk(args: dict) -> Risk:
    return Risk.CONFIRM if args.get("setting") == "wifi" and not args.get("on") else Risk.SAFE


def _toggle_summary(args: dict) -> str:
    text = f"turn {args.get('setting')} {'on' if args.get('on') else 'off'}"
    if args.get("setting") == "wifi" and not args.get("on"):
        text += " (this also disconnects Wisp)"
    return text


# ----- media -------------------------------------------------------------------------------------
async def media_tool(ctx: ToolContext, args: dict) -> dict:
    import asyncio

    watcher = ctx.services.media
    action = args["action"]
    if action == "status":
        state = watcher.state
        if not state.active:
            return {"playing": False, "note": "Nothing is playing."}
        return {"title": state.title, "artist": state.artist, "playing": state.playing,
                "position_s": round(state.position), "duration_s": round(state.duration)}
    ok = await asyncio.wrap_future(watcher.command(action))
    if not ok:
        raise ToolError("No media app accepted that command (is something playing?).")
    return {"done": action}


# ----- power -------------------------------------------------------------------------------------
def power_tool(ctx: ToolContext, args: dict) -> dict:
    action = args["action"]
    {"lock": power.lock, "sleep": power.sleep, "restart": power.restart,
     "shutdown": power.shutdown}[action]()
    return {"done": action}


def _power_risk(args: dict) -> Risk:
    return Risk.SAFE if args.get("action") == "lock" else Risk.CONFIRM


# ----- clipboard ---------------------------------------------------------------------------------
def copy_tool(ctx: ToolContext, args: dict) -> dict:
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.clipboard().setText(args["text"])
    return {"copied_chars": len(args["text"])}


def clipboard_history_tool(ctx: ToolContext, args: dict) -> dict:
    limit = max(1, min(args.get("limit", 10), 30))
    items = ctx.services.clipboard.items(args.get("query", ""), limit)
    return {"items": [{"id": i.id, "kind": i.kind, "preview": i.preview} for i in items]}


def wallpaper_tool(ctx: ToolContext, args: dict) -> dict:
    """The desktop wallpaper. ``set`` only picks among the images Wisp lists (Pictures and
    Windows' own wallpapers), matched by name."""
    action = args.get("action", "current")
    if action == "current":
        from pathlib import Path

        return {"current": Path(wallpaper.current()).name or "a solid colour"}
    images = wallpaper.list_images()
    if action == "list":
        return {"images": [image.stem for image in images[:40]], "more": len(images) > 40}
    wanted = (args.get("image") or "").strip().lower()
    if not wanted:
        raise ToolError("Say which image (call wallpaper with action=list to see them).")
    scored = [(fuzz.WRatio(wanted, image.stem.lower()), image) for image in images]
    score, best = max(scored, default=(0, None), key=lambda pair: pair[0])
    if best is None or score < 70:
        raise ToolError(f"No wallpaper image matches '{wanted}'.")
    try:
        wallpaper.set_wallpaper(str(best))
    except (OSError, ValueError) as exc:
        raise ToolError(str(exc)) from exc
    return {"wallpaper": best.name}


def tools() -> list[Tool]:
    amount = integer("Level 0-100 for set, or step for up/down (default 10)")
    return [
        Tool("volume", "Get or change the system volume, or mute/unmute.",
             obj({"action": string("What to do", ["get", "set", "up", "down", "mute", "unmute"]),
                  "level": amount}, ["action"]),
             volume_tool, "system"),
        Tool("brightness", "Get or change laptop screen brightness.",
             obj({"action": string("What to do", ["get", "set", "up", "down"]), "level": amount},
                 ["action"]),
             brightness_tool, "system"),
        Tool("toggle_setting", "Turn Wi-Fi, Bluetooth, dark mode or Night Light on or off.",
             obj({"setting": string("Setting", ["wifi", "bluetooth", "dark_mode", "night_light"]),
                  "on": boolean("true = on")}, ["setting", "on"]),
             toggle_tool, "system", runs_on="async", risk_fn=_toggle_risk,
             summary=_toggle_summary),
        Tool("wallpaper", "The desktop wallpaper: what it is, which images there are "
             "(Pictures and Windows wallpapers), or set one by name.",
             obj({"action": string("What to do", ["current", "list", "set"]),
                  "image": string("For set: the image's name")}, ["action"]),
             wallpaper_tool, "system", summary=lambda a: f"set the wallpaper to "
             f"'{a.get('image')}'" if a.get("action") == "set" else "check the wallpaper"),
        Tool("output_device", "List audio output devices, or switch the default to one by name.",
             obj({"name": string("Device to switch to; omit to list")}), output_device_tool,
             "system"),
        Tool("media", "Control or check the music/video playing in any app.",
             obj({"action": string("What to do", ["status", "play_pause", "play", "pause",
                                                  "next", "previous"])}, ["action"]),
             media_tool, "media", runs_on="async"),
        Tool("power", "Lock, sleep, restart or shut down the PC (all but lock need "
             "confirmation).",
             obj({"action": string("What to do", ["lock", "sleep", "restart", "shutdown"])},
                 ["action"]),
             power_tool, "power", risk_fn=_power_risk,
             summary=lambda a: f"{a.get('action')} the PC"),
        Tool("copy_to_clipboard", "Put text on the clipboard.",
             obj({"text": string("Text to copy")}, ["text"]), copy_tool, "clipboard",
             runs_on="ui", escalate_when_tainted=True,
             summary=lambda a: f"copy '{a.get('text', '')[:60]}' to the clipboard"),
        Tool("clipboard_history", "Recent clipboard items, optionally filtered by text.",
             obj({"query": string("Text to search for"), "limit": integer("Max items")}),
             clipboard_history_tool, "clipboard", untrusted_output=True, schedulable=False),
    ]
