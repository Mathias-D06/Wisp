"""Hold-chord parsing, conflict detection and the key-event state machine.

A chord such as ``ctrl+win`` fires only when exactly its keys are held, with no other key, for
``hold_ms`` (default 250 ms). Pressing any other key while it is armed or active cancels it and
"spoils" it until all its keys are released, so Ctrl+Win+Right (switch desktop) or
Ctrl+Shift+T keep working normally. Pure logic: no Windows calls, fully unit-tested.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

GENERIC = {
    "ctrl": frozenset({0x11, 0xA2, 0xA3}),
    "shift": frozenset({0x10, 0xA0, 0xA1}),
    "alt": frozenset({0x12, 0xA4, 0xA5}),
    "win": frozenset({0x5B, 0x5C}),
}
SIDED = {
    "lctrl": 0xA2, "rctrl": 0xA3, "lshift": 0xA0, "rshift": 0xA1,
    "lalt": 0xA4, "ralt": 0xA5, "lwin": 0x5B, "rwin": 0x5C,
}
MODIFIER_VKS = frozenset().union(*GENERIC.values())
KEYS: dict[str, int] = {
    "space": 0x20, "pause": 0x13, "capslock": 0x14, "apps": 0x5D, "insert": 0x2D,
    "scrolllock": 0x91, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
    **{chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
}
DISPLAY = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "win": "Win"}

# Windows shortcuts a hold-chord must not equal (they would be swallowed or never seen).
RESERVED = {
    frozenset({"win", "l"}), frozenset({"win", "d"}), frozenset({"win", "e"}),
    frozenset({"win", "r"}), frozenset({"win", "v"}), frozenset({"win", "tab"}),
    frozenset({"alt", "tab"}), frozenset({"alt", "f4"}), frozenset({"ctrl", "c"}),
    frozenset({"ctrl", "v"}), frozenset({"ctrl", "x"}), frozenset({"ctrl", "z"}),
    frozenset({"ctrl", "a"}), frozenset({"ctrl", "s"}), frozenset({"win", "shift", "s"}),
    frozenset({"win", "g"}), frozenset({"win", "i"}),
}


class ChordError(ValueError):
    pass


@dataclass(frozen=True)
class Chord:
    text: str
    modifiers: frozenset[str]  # generic or sided modifier names
    key: str | None = None  # at most one non-modifier key

    @property
    def tokens(self) -> frozenset[str]:
        return self.modifiers | ({self.key} if self.key else set())

    @property
    def key_vk(self) -> int | None:
        return KEYS[self.key] if self.key else None

    def vk_groups(self) -> list[frozenset[int]]:
        groups = [GENERIC[m] if m in GENERIC else frozenset({SIDED[m]}) for m in self.modifiers]
        if self.key:
            groups.append(frozenset({KEYS[self.key]}))
        return groups

    def matches(self, pressed: set[int]) -> bool:
        """True when ``pressed`` is exactly this chord: every group has a pressed key and
        every pressed key belongs to some group."""
        if not pressed:
            return False
        groups = self.vk_groups()
        if not all(group & pressed for group in groups):
            return False
        allowed = frozenset().union(*groups)
        return pressed <= allowed

    def needs_mask(self) -> bool:
        """Win or Alt held alone open Start / the menu bar on release; Ctrl+Shift and Alt+Shift
        switch keyboard layout. Tapping an unassigned key while held prevents both."""
        base = {m.lstrip("lr") if m in SIDED else m for m in self.modifiers}
        return bool(base & {"win", "alt"}) or base >= {"ctrl", "shift"} or base >= {"alt", "shift"}

    def display(self) -> str:
        parts = [DISPLAY.get(m, m.upper()) for m in sorted(self.modifiers, key=_order)]
        if self.key:
            parts.append(self.key.capitalize() if len(self.key) > 1 else self.key.upper())
        return " + ".join(parts)


def _order(name: str) -> int:
    base = name.lstrip("lr") if name in SIDED else name
    return ["ctrl", "shift", "alt", "win"].index(base) if base in DISPLAY else 9


def parse_chord(text: str) -> Chord:
    parts = [p.strip().lower() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ChordError("Hotkey is empty.")
    aliases = {"control": "ctrl", "windows": "win", "super": "win", "meta": "win", "option": "alt"}
    parts = [aliases.get(p, p) for p in parts]
    modifiers: set[str] = set()
    key: str | None = None
    for part in parts:
        if part in GENERIC or part in SIDED:
            modifiers.add(part)
        elif part in KEYS:
            if key is not None:
                raise ChordError("A hotkey can include only one non-modifier key.")
            key = part
        else:
            raise ChordError(f"Unknown key '{part}'.")
    if len(parts) != len(set(parts)):
        raise ChordError("A key is repeated.")
    if not modifiers and key is None:
        raise ChordError("Hotkey is empty.")
    if not modifiers and key and len(key) == 1:
        raise ChordError("Holding a single letter or digit would interfere with typing.")
    if len(modifiers) == 1 and key is None:
        (only,) = modifiers
        base = only.lstrip("lr") if only in SIDED else only
        if base in ("shift", "ctrl", "alt") and only in GENERIC:
            raise ChordError(f"Holding {DISPLAY[base]} alone is used for typing; add another key.")
    return Chord(text=text, modifiers=frozenset(modifiers), key=key)


def find_conflicts(chords: dict[str, str]) -> list[str]:
    """Problems with a set of named hotkeys (empty list = fine)."""
    problems: list[str] = []
    parsed: dict[str, Chord] = {}
    for name, text in chords.items():
        try:
            parsed[name] = parse_chord(text)
        except ChordError as exc:
            problems.append(f"{name}: {exc}")
    for name, chord in parsed.items():
        if chord.tokens in RESERVED:
            problems.append(f"{name}: {chord.display()} is a Windows shortcut.")
    names = list(parsed)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            a, b = parsed[first], parsed[second]
            if a.tokens == b.tokens:
                problems.append(f"{first} and {second} use the same keys ({a.display()}).")
            elif _overlaps(a, b):
                problems.append(
                    f"{first} ({a.display()}) and {second} ({b.display()}) overlap: one is "
                    "part of the other."
                )
    return problems


def _overlaps(a: Chord, b: Chord) -> bool:
    def expand(chord: Chord) -> frozenset[str]:
        return frozenset(m.lstrip("lr") if m in SIDED else m for m in chord.modifiers) | (
            {chord.key} if chord.key else frozenset())

    ea, eb = expand(a), expand(b)
    return ea < eb or eb < ea


Event = Callable[[str, str], None]  # (chord name, "press" | "release" | "cancel")


@dataclass
class _ChordState:
    chord: Chord
    phase: str = "idle"  # idle | armed | active | spoiled
    arm_id: int = 0
    suppressed_key_down: bool = False


@dataclass
class ChordMachine:
    """Feed raw key events; get press/release/cancel events. Thread-safe."""

    chords: dict[str, Chord]
    hold_ms: int
    emit: Event
    schedule: Callable[[float, Callable[[], None]], Any]
    on_activate: Callable[[Chord], None] = lambda chord: None
    replay_key: Callable[[int], None] = lambda vk: None
    pressed: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._states = {name: _ChordState(chord) for name, chord in self.chords.items()}

    def key_event(self, vk: int, down: bool) -> bool:
        """Process one physical key event. Returns True if it must be suppressed."""
        with self._lock:
            if down:
                if vk in self.pressed:
                    return self._suppress_repeat(vk)  # auto-repeat
                self.pressed.add(vk)
            else:
                self.pressed.discard(vk)
            suppress = False
            for name, state in self._states.items():
                suppress |= self._update(name, state, vk, down)
            return suppress

    def _suppress_repeat(self, vk: int) -> bool:
        return any(s.chord.key_vk == vk and s.phase in ("armed", "active")
                   for s in self._states.values())

    def _update(self, name: str, state: _ChordState, vk: int, down: bool) -> bool:
        chord = state.chord
        in_chord = any(vk in group for group in chord.vk_groups())
        exact = chord.matches(self.pressed)
        is_chord_key = chord.key_vk == vk
        if state.phase == "spoiled":
            if not any(any(k in g for g in chord.vk_groups()) for k in self.pressed):
                state.phase = "idle"
            if exact and down and state.phase == "idle":
                return self._arm(name, state, vk)
            return False
        if state.phase == "idle":
            if exact and down:
                return self._arm(name, state, vk)
            return False
        if state.phase == "armed":
            if exact:
                return is_chord_key
            # Another key pressed → spoiled; a chord key released early → just a short tap.
            state.phase = "spoiled" if down else "idle"
            state.arm_id += 1
            if is_chord_key and not down and state.suppressed_key_down:
                # Quick tap of a chord with a normal key: give the key back to the app.
                state.suppressed_key_down = False
                self.replay_key(vk)
                return True
            return False
        if state.phase == "active":
            if down and not in_chord:
                state.phase = "spoiled"
                self.emit(name, "cancel")
                return False
            if not down and in_chord:
                state.phase = "idle" if not self.pressed else "spoiled"
                state.suppressed_key_down = False
                self.emit(name, "release")
                return is_chord_key
            return is_chord_key
        return False

    def _arm(self, name: str, state: _ChordState, vk: int) -> bool:
        state.phase = "armed"
        state.arm_id += 1
        arm_id = state.arm_id
        state.suppressed_key_down = state.chord.key_vk == vk
        self.schedule(self.hold_ms / 1000.0, lambda: self._fire(name, arm_id))
        return state.suppressed_key_down

    def _fire(self, name: str, arm_id: int) -> None:
        with self._lock:
            state = self._states[name]
            if state.phase != "armed" or state.arm_id != arm_id:
                return
            if not state.chord.matches(self.pressed):
                state.phase = "idle"
                return
            state.phase = "active"
        if state.chord.needs_mask():
            self.on_activate(state.chord)
        self.emit(name, "press")

    def is_active(self, name: str) -> bool:
        with self._lock:
            return self._states[name].phase == "active"

    def reset(self) -> None:
        with self._lock:
            self.pressed.clear()
            for state in self._states.values():
                state.phase = "idle"
                state.arm_id += 1
