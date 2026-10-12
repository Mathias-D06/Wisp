"""The set of tools and which of them are offered to the model."""

from __future__ import annotations

from typing import Any

from wisp.settings import Settings
from wisp.tools.base import Risk, Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool {tool.name}")
        self._tools[tool.name] = tool

    def register_all(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def is_offered(self, tool: Tool, settings: Settings) -> bool:
        """Whether the model sees this tool: its skill group is on and, for disabled-by-default
        tools, the Safety toggle is on. The dispatcher re-checks on every call."""
        if tool.group not in settings.loadout.skills and tool.group != "core":
            return False
        if tool.risk == Risk.DISABLED:
            return bool(tool.enabled_by and getattr(settings.safety, tool.enabled_by, False))
        return True

    def declarations(self, settings: Settings) -> list[dict[str, Any]]:
        return [t.declaration() for t in self._tools.values() if self.is_offered(t, settings)]

    def groups(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for tool in self._tools.values():
            result.setdefault(tool.group, []).append(tool.name)
        return result
