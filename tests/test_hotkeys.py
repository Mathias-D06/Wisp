"""Unit tests for hold-chord parsing, conflicts and the key-event state machine."""

from __future__ import annotations

import pytest

from wisp.hotkeys.chords import ChordError, ChordMachine, find_conflicts, parse_chord

CTRL, LCTRL, SHIFT_L, WIN, ALT_L, KEY_D, KEY_T, SPACE, F9 = (
    0x11, 0xA2, 0xA0, 0x5B, 0xA4, 0x44, 0x54, 0x20, 0x78)
RIGHT = 0x27


class Timers:
    def __init__(self):
        self.pending = []

    def schedule(self, delay, fn):
        self.pending.append(fn)

    def fire(self):
        pending, self.pending = self.pending, []
        for fn in pending:
            fn()


def machine(**chords):
    events, masks, replays = [], [], []
    timers = Timers()
    m = ChordMachine(
        chords={k: parse_chord(v) for k, v in chords.items()}, hold_ms=250,
        emit=lambda name, kind: events.append((name, kind)), schedule=timers.schedule,
        on_activate=lambda chord: masks.append(chord.text), replay_key=replays.append,
    )
    return m, events, timers, masks, replays


def test_parse_and_display():
    chord = parse_chord("Ctrl + Win")
    assert chord.modifiers == {"ctrl", "win"} and chord.key is None
    assert chord.display() == "Ctrl + Win"
    assert parse_chord("ctrl+space").key == "space"
    assert parse_chord("rctrl").modifiers == {"rctrl"}


@pytest.mark.parametrize("bad", ["", "ctrl+ctrl", "shift", "ctrl", "a", "ctrl+a+b", "hyper+x"])
def test_parse_rejects(bad):
    with pytest.raises(ChordError):
        parse_chord(bad)


def test_conflicts():
    assert find_conflicts({"ptt": "alt+win", "dictation": "ctrl+win", "circle": "ctrl+shift"}) == []
    problems = find_conflicts({"a": "ctrl+win", "b": "win+ctrl"})
    assert any("same keys" in p for p in problems)
    problems = find_conflicts({"a": "ctrl+shift", "b": "ctrl+shift+alt"})
    assert any("overlap" in p for p in problems)
    assert any("Windows shortcut" in p for p in find_conflicts({"a": "win+l"}))
    assert any("Unknown key" in p for p in find_conflicts({"a": "ctrl+nope"}))


def test_hold_fires_after_timer_and_release_emits():
    m, events, timers, masks, _ = machine(dictation="ctrl+win")
    assert not m.key_event(LCTRL, True)
    assert not m.key_event(WIN, True)
    timers.fire()
    assert events == [("dictation", "press")]
    assert masks == ["ctrl+win"]  # Start menu suppression requested
    m.key_event(WIN, False)
    assert events[-1] == ("dictation", "release")


def test_short_tap_does_nothing():
    m, events, timers, masks, _ = machine(dictation="ctrl+win")
    m.key_event(LCTRL, True)
    m.key_event(WIN, True)
    m.key_event(WIN, False)  # released before the 250 ms timer
    timers.fire()
    assert events == [] and masks == []


def test_other_key_while_armed_spoils_chord():
    """Ctrl+Win+Right (switch virtual desktop) must pass through untouched."""
    m, events, timers, _, _ = machine(dictation="ctrl+win")
    m.key_event(LCTRL, True)
    m.key_event(WIN, True)
    assert not m.key_event(RIGHT, True)
    timers.fire()
    m.key_event(RIGHT, False)
    timers.fire()  # still holding ctrl+win after releasing Right: must not re-arm
    assert events == []
    m.key_event(WIN, False)
    m.key_event(LCTRL, False)
    m.key_event(LCTRL, True)
    m.key_event(WIN, True)
    timers.fire()
    assert events == [("dictation", "press")]


def test_other_key_while_active_cancels():
    m, events, timers, _, _ = machine(circle="ctrl+shift")
    m.key_event(LCTRL, True)
    m.key_event(SHIFT_L, True)
    timers.fire()
    assert m.key_event(KEY_T, True) is False  # Ctrl+Shift+T reaches the app
    assert events == [("circle", "press"), ("circle", "cancel")]
    m.key_event(KEY_T, False)
    m.key_event(SHIFT_L, False)
    assert events == [("circle", "press"), ("circle", "cancel")]


def test_extra_modifier_means_different_chord():
    m, events, timers, _, _ = machine(circle="ctrl+shift", ptt="alt+win")
    m.key_event(LCTRL, True)
    m.key_event(SHIFT_L, True)
    m.key_event(ALT_L, True)
    timers.fire()
    assert events == []


def test_autorepeat_is_ignored():
    m, events, timers, _, _ = machine(ptt="alt+win")
    m.key_event(ALT_L, True)
    m.key_event(WIN, True)
    for _ in range(5):
        m.key_event(WIN, True)
    timers.fire()
    assert events == [("ptt", "press")]


def test_chord_with_normal_key_suppresses_and_replays_quick_tap():
    m, events, timers, _, replays = machine(ptt="ctrl+space")
    m.key_event(LCTRL, True)
    assert m.key_event(SPACE, True) is True  # swallowed while armed
    assert m.key_event(SPACE, False) is True
    assert replays == [SPACE]  # quick tap handed back to the app
    m.key_event(SPACE, True)
    timers.fire()
    assert events == [("ptt", "press")]
    assert m.key_event(SPACE, False) is True
    assert events[-1] == ("ptt", "release")


def test_single_function_key_chord():
    m, events, timers, masks, _ = machine(ptt="f9")
    assert m.key_event(F9, True) is True
    timers.fire()
    assert events == [("ptt", "press")] and masks == []
    assert m.key_event(F9, False) is True
    assert events[-1] == ("ptt", "release")


def test_generic_ctrl_matches_either_side():
    m, events, timers, _, _ = machine(dictation="ctrl+win")
    m.key_event(0xA3, True)  # right ctrl
    m.key_event(0x5C, True)  # right win
    timers.fire()
    assert events == [("dictation", "press")]


def test_mask_rules():
    assert parse_chord("ctrl+win").needs_mask()
    assert parse_chord("ctrl+shift").needs_mask()
    assert parse_chord("alt+win").needs_mask()
    assert not parse_chord("f9").needs_mask()
    assert not parse_chord("ctrl+space").needs_mask()
