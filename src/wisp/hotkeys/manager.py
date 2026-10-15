"""Connects the keyboard hook to the settings and delivers events on the Qt thread."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from wisp.hotkeys.chords import Chord, ChordError, parse_chord
from wisp.hotkeys.hook import KeyboardHook
from wisp.settings import Settings

log = logging.getLogger(__name__)

HOTKEY_NAMES = ("push_to_talk", "dictation", "circle", "island", "screen_assist", "watch")


class HotkeySignals(QObject):
    event = Signal(str, str)  # (name, "arm" | "disarm" | "press" | "release" | "cancel")


class HotkeyManager:
    def __init__(self) -> None:
        self.signals = HotkeySignals()
        self.hook = KeyboardHook(emit=self.signals.event.emit)
        self.chords: dict[str, Chord] = {}

    def apply(self, settings: Settings) -> list[str]:
        problems = []
        chords: dict[str, Chord] = {}
        for name in HOTKEY_NAMES:
            text = getattr(settings.hotkeys, name)
            try:
                chords[name] = parse_chord(text)
            except ChordError as exc:
                problems.append(f"{name}: {exc}")
                log.error("Hotkey %s=%r ignored: %s", name, text, exc)
        self.chords = chords
        self.hook.configure(chords, settings.hotkeys.hold_ms)
        return problems

    def start(self) -> str | None:
        if not self.hook.start():
            return self.hook.error
        return None

    def stop(self) -> None:
        self.hook.stop()

    def display(self, name: str) -> str:
        chord = self.chords.get(name)
        return chord.display() if chord else "(not set)"
