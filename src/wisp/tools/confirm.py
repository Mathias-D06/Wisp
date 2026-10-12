"""Pending confirmations, resolved by a click or by the user's own words.

Evidence for a spoken "yes" comes from the user's input transcription (or text typed in the
console), never from the model. The latest pending action created before the utterance is the
one the reply applies to.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from wisp.tools.base import Origin

State = Literal["pending", "approved", "rejected", "expired", "done"]

_YES = [
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "do it", "go ahead", "confirm",
    "confirmed", "please do", "affirmative", "correct", "that's right", "go for it", "proceed",
    "sí", "si", "oui", "ja", "sì", "sim", "tak", "evet", "haan", "はい", "네", "是", "好", "да",
]
_NO = [
    "no", "nope", "don't", "do not", "cancel", "stop", "never mind", "nevermind", "wait",
    "abort", "not now", "no thanks", "non", "nein", "nee", "nie", "hayır", "いいえ", "아니",
    "不", "нет",
]


def _pattern(words: list[str]) -> re.Pattern[str]:
    escaped = sorted((re.escape(w) for w in words), key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(escaped) + r")(?!\w)", re.IGNORECASE)


_YES_RE = _pattern(_YES)
_NO_RE = _pattern(_NO)


def classify_reply(text: str) -> Literal["yes", "no"] | None:
    """Very short, explicit replies only; anything long or mixed is not treated as consent."""
    cleaned = text.strip().lower().replace("’", "'")
    if not cleaned:
        return None
    if _NO_RE.search(cleaned):
        return "no"
    words = re.findall(r"\w+", cleaned)
    if len(words) <= 6 and _YES_RE.search(cleaned):
        return "yes"
    return None


@dataclass
class PendingAction:
    id: str
    tool: str
    args: dict[str, Any]
    summary: str
    origin: Origin
    created: float
    expires: float
    state: State = "pending"
    evidence: str | None = None
    result: dict[str, Any] | None = None
    resolved_at: float | None = None
    event: threading.Event = field(default_factory=threading.Event, repr=False)


Listener = Callable[[str, PendingAction], None]


class ConfirmationManager:
    def __init__(self, ttl_seconds: float = 120.0, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._items: dict[str, PendingAction] = {}
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _emit(self, event: str, item: PendingAction) -> None:
        for listener in list(self._listeners):
            listener(event, item)

    def create(self, tool: str, args: dict[str, Any], summary: str, origin: Origin,
               ttl: float | None = None) -> PendingAction:
        now = self._clock()
        with self._lock:
            self._expire_old(now)
            item = PendingAction(
                id=secrets.token_hex(3), tool=tool, args=dict(args), summary=summary,
                origin=origin, created=now, expires=now + (ttl or self._ttl),
            )
            self._items[item.id] = item
        self._emit("created", item)
        return item

    def get(self, item_id: str) -> PendingAction | None:
        with self._lock:
            self._expire_old(self._clock())
            return self._items.get(item_id)

    def pending(self) -> list[PendingAction]:
        with self._lock:
            self._expire_old(self._clock())
            return [i for i in self._items.values() if i.state == "pending"]

    def _expire_old(self, now: float) -> None:
        expired = []
        for item in self._items.values():
            if item.state == "pending" and now > item.expires:
                item.state = "expired"
                item.resolved_at = now
                item.event.set()
                expired.append(item)
        for item in expired:
            self._emit("expired", item)
        stale = [k for k, v in self._items.items() if v.state != "pending" and v.resolved_at
                 and now - v.resolved_at > 600]
        for key in stale:
            del self._items[key]

    def _resolve(self, item: PendingAction, state: State, evidence: str) -> bool:
        with self._lock:
            if item.state != "pending":
                return False
            item.state = state
            item.evidence = evidence
            item.resolved_at = self._clock()
            item.event.set()
        self._emit(state, item)
        return True

    def approve_click(self, item_id: str) -> bool:
        item = self.get(item_id)
        return bool(item) and self._resolve(item, "approved", "click")

    def reject_click(self, item_id: str) -> bool:
        item = self.get(item_id)
        return bool(item) and self._resolve(item, "rejected", "click")

    def on_user_utterance(self, text: str, at: float | None = None) -> PendingAction | None:
        """Apply a spoken/typed reply to the newest pending action created before it."""
        verdict = classify_reply(text)
        if verdict is None:
            return None
        at = self._clock() if at is None else at
        with self._lock:
            self._expire_old(at)
            candidates = [i for i in self._items.values()
                          if i.state == "pending" and i.created <= at and i.origin == Origin.VOICE]
            if not candidates:
                return None
            item = max(candidates, key=lambda i: i.created)
        state: State = "approved" if verdict == "yes" else "rejected"
        self._resolve(item, state, f"voice: {text.strip()[:60]}")
        return item

    def mark_done(self, item: PendingAction, result: dict[str, Any]) -> None:
        with self._lock:
            item.state = "done"
            item.result = result
            item.resolved_at = self._clock()
        self._emit("done", item)

    def find_approved(self, tool: str, args: dict[str, Any]) -> PendingAction | None:
        with self._lock:
            for item in self._items.values():
                if item.state == "approved" and item.tool == tool and item.args == args:
                    return item
        return None

    def wait(self, item: PendingAction, timeout: float) -> State:
        item.event.wait(timeout)
        with self._lock:
            if item.state == "pending" and self._clock() > item.expires:
                self._expire_old(self._clock())
            return item.state
