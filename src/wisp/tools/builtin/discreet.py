"""Discreet mode by voice (skill group "core", D-053): "go discreet", "back to normal"."""

from __future__ import annotations

from wisp.tools.base import Tool, ToolContext, ToolError, boolean, obj


def discreet_mode(ctx: ToolContext, args: dict) -> dict:
    mode = getattr(ctx.services, "discreet", None)
    if mode is None:
        raise ToolError("Discreet mode isn't available.")
    on = bool(args.get("on", True))
    mode.set_enabled(on, "voice")
    if on:
        return {"discreet": True,
                "note": "From now on replies appear as quiet text under the island, not spoken; "
                        "confirm with a few words or not at all."}
    return {"discreet": False, "note": "Spoken replies and the normal island are back."}


def tools() -> list[Tool]:
    return [
        Tool("discreet_mode", "Turn Discreet mode on ('go discreet', 'be quiet', 'I'm in a "
             "lecture') or off ('back to normal'). On: the island becomes a small grey line, "
             "replies are text only and banners turn into a subtle pulse.",
             obj({"on": boolean("True to turn it on, false to turn it off")}, ["on"]),
             discreet_mode, "core", runs_on="ui", schedulable=False,
             summary=lambda a: "go discreet" if a.get("on", True) else "leave Discreet mode"),
    ]
