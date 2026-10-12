"""Core tools that are always available."""

from __future__ import annotations

from datetime import datetime

from wisp.tools.base import Tool, ToolContext, obj


def get_current_time(ctx: ToolContext, args: dict) -> dict:
    now = datetime.now().astimezone()
    return {
        "local_time": now.isoformat(timespec="minutes"),
        "weekday": now.strftime("%A"),
        "timezone": now.tzname(),
    }


def tools() -> list[Tool]:
    return [
        Tool(
            name="get_current_time",
            description="Current local date, time, weekday and timezone.",
            parameters=obj(),
            handler=get_current_time,
            group="core",
        )
    ]
