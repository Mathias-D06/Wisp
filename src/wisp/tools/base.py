"""Tool definition, risk tiers and the context handlers receive."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal


class Risk(StrEnum):
    SAFE = "safe"
    CONFIRM = "confirm"
    DISABLED = "disabled"  # disabled by default; needs a Settings toggle


class Origin(StrEnum):
    VOICE = "voice"  # requested by the model during a conversation (voice or console)
    SCHEDULE = "schedule"  # replayed by a scheduled task / routine
    UI = "ui"  # the user clicked a control in Wisp's own UI


class ToolError(Exception):
    """A failure the user/model should hear about in plain words."""


@dataclass
class ToolContext:
    origin: Origin
    services: Any
    call_id: str | None = None


Handler = Callable[[ToolContext, dict[str, Any]], Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler
    group: str
    risk: Risk = Risk.SAFE
    risk_fn: Callable[[dict[str, Any]], Risk] | None = None
    enabled_by: str | None = None
    """For DISABLED tools: the SafetySettings flag that enables them."""
    tier_when_enabled: Risk = Risk.CONFIRM
    untrusted_output: bool = False
    """Result contains text from the screen, files or web pages (data, never instructions)."""
    escalate_when_tainted: bool = False
    """A SAFE tool that needs confirmation right after untrusted content was read."""
    summary: Callable[[dict[str, Any]], str] | None = None
    runs_on: Literal["worker", "ui", "async"] = "worker"
    timeout_s: float = 30.0
    schedulable: bool = True

    def describe(self, args: dict[str, Any]) -> str:
        if self.summary:
            try:
                return self.summary(args)
            except Exception:
                return self.name
        shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
        return f"{self.name}({shown})"

    def declaration(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def obj(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict:
    """Shorthand for an OpenAPI-subset object schema (type/properties/required)."""
    schema: dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        schema["required"] = required
    return schema


def string(description: str, enum: list[str] | None = None) -> dict:
    schema: dict[str, Any] = {"type": "string", "description": description}
    if enum:
        schema["enum"] = enum
    return schema


def integer(description: str) -> dict:
    return {"type": "integer", "description": description}


def boolean(description: str) -> dict:
    return {"type": "boolean", "description": description}


def array(items: dict, description: str) -> dict:
    return {"type": "array", "items": items, "description": description}
