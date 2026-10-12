"""Safety layer: decides allow / confirm / deny for every tool call, in code, not in the prompt.

Rules (README "Safety model"):
* DISABLED-tier tools (terminal, raw mouse/keyboard) are refused unless their Safety toggle is on.
* CONFIRM-tier tools need a spoken "yes" or a click. A user may auto-approve specific
  confirm-tier tools, but never while the session is "tainted".
* Tainted = untrusted content (screen text, files, web pages) was read in the last N minutes.
  While tainted, every confirm-tier call asks, and SAFE tools marked ``escalate_when_tainted``
  (typing, clicking, opening URLs) also ask.
* Scheduled routines never use auto-approval.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from wisp.settings import Settings
from wisp.tools.base import Origin, Risk, Tool


@dataclass(frozen=True)
class Decision:
    action: Literal["allow", "confirm", "deny"]
    reason: str
    tier: Risk


class TaintTracker:
    """Remembers when untrusted content was last read."""

    def __init__(self, minutes: Callable[[], int], clock: Callable[[], float] = time.monotonic):
        self._minutes = minutes
        self._clock = clock
        self._lock = threading.Lock()
        self._marked_at: float | None = None
        self._source: str | None = None

    def mark(self, source: str) -> None:
        with self._lock:
            self._marked_at = self._clock()
            self._source = source

    def clear(self) -> None:
        with self._lock:
            self._marked_at = None
            self._source = None

    def is_tainted(self) -> bool:
        with self._lock:
            if self._marked_at is None:
                return False
            return self._clock() - self._marked_at < self._minutes() * 60

    @property
    def source(self) -> str | None:
        return self._source if self.is_tainted() else None


class SafetyPolicy:
    def __init__(self, settings: Callable[[], Settings], taint: TaintTracker):
        self._settings = settings
        self.taint = taint

    def effective_tier(self, tool: Tool, args: dict[str, Any]) -> Risk:
        tier = tool.risk_fn(args) if tool.risk_fn else tool.risk
        if tool.risk == Risk.DISABLED and tier == Risk.DISABLED:
            return Risk.DISABLED
        return tier

    def decide(self, tool: Tool, args: dict[str, Any], origin: Origin) -> Decision:
        settings = self._settings()
        skill_off = tool.group != "core" and tool.group not in settings.loadout.skills
        if origin != Origin.UI and skill_off:
            return Decision("deny", f"The '{tool.group}' skill is switched off in the Loadout.",
                            tool.risk)
        tier = self.effective_tier(tool, args)
        if tool.risk == Risk.DISABLED:
            enabled = bool(tool.enabled_by and getattr(settings.safety, tool.enabled_by, False))
            if not enabled:
                return Decision(
                    "deny",
                    f"{tool.name} is disabled. The user can enable it in Settings → Safety.",
                    Risk.DISABLED,
                )
            tier = tool.risk_fn(args) if tool.risk_fn else tool.tier_when_enabled
            if tier == Risk.DISABLED:
                tier = tool.tier_when_enabled
        tainted = self.taint.is_tainted()
        if tier == Risk.CONFIRM:
            if tainted:
                return Decision("confirm", "Untrusted content was read recently.", tier)
            if origin == Origin.VOICE and tool.name in settings.safety.auto_approve:
                return Decision("allow", "Auto-approved in Settings → Safety.", tier)
            return Decision("confirm", "This action needs your OK.", tier)
        if tainted and tool.escalate_when_tainted and origin != Origin.UI:
            return Decision(
                "confirm", "Untrusted content was read recently; confirming before acting.",
                Risk.CONFIRM,
            )
        return Decision("allow", "Safe action.", tier)
