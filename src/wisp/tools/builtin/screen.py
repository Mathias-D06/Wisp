"""look_at_screen (skill group "screen").

The Live API documents images as realtime video frames (JPEG, ≤1 fps); function responses with
images are documented only for generateContent, so the screenshot is sent as a frame just before
the tool result (DECISIONS.md D-017).
"""

from __future__ import annotations

import time

from wisp.tools.base import Tool, ToolContext, ToolError, obj, string
from wisp.winapi import screen
from wisp.winapi import windows as win
from wisp.winapi.uia import SECURE_DESKTOP_MESSAGE

FRAME_LEAD_SECONDS = 0.3


def _target_window() -> win.WindowInfo | None:
    candidates = win.list_windows()
    fg = win.foreground_window()
    if fg and fg.hwnd in {w.hwnd for w in candidates}:
        return fg
    return candidates[0] if candidates else None


def look_at_screen(ctx: ToolContext, args: dict) -> dict:
    if ctx.services.live is None:
        raise ToolError("The voice session is not available.")
    if not win.input_desktop_available():
        raise ToolError(SECURE_DESKTOP_MESSAGE)
    target = args.get("target", "screen")
    window = _target_window()
    if target == "window":
        if window is None:
            raise ToolError("There is no open window to look at.")
        bounds = win.frame_bounds(window.hwnd)
        region = screen.clamp_to_screens(bounds) if bounds else None
        if region is None:
            raise ToolError("That window is minimised or off-screen.")
        label = f"the '{window.title}' window"
    else:
        if window is not None and (bounds := win.frame_bounds(window.hwnd)):
            x, y = (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2
        else:
            x, y = screen.cursor_position()
        region = screen.monitor_at(x, y)
        label = "the screen"
    shot = screen.capture(region)
    ctx.services.live.send_image(shot.jpeg)
    ctx.services.last_capture = (shot, time.monotonic())
    time.sleep(FRAME_LEAD_SECONDS)
    return {
        "captured": label,
        "image_pixels": f"{shot.image_size[0]}x{shot.image_size[1]}",
        "how": "The screenshot was just sent to you as an image. Answer from it.",
    }


def tools() -> list[Tool]:
    return [
        Tool(
            name="look_at_screen",
            description="See the user's screen (or the active window) to answer about it.",
            parameters=obj({"target": string("What to capture", ["screen", "window"])}),
            handler=look_at_screen,
            group="screen",
            untrusted_output=True,
            schedulable=False,
        )
    ]
