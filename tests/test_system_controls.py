"""Phase 7 system layer: pure parsing/maths and tool logic with the real system calls replaced.

Write paths that would change this PC (Night Light, Wi-Fi, theme, volume, output device, power)
are only exercised through pure functions or monkeypatched fakes; MANUAL_TESTS.md F7 covers the
real effect.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from wisp.system import controls
from wisp.system.controls import (
    ControlUnavailable,
    OutputDevice,
    parse_night_light,
    toggle_night_light_blob,
)
from wisp.system.media import MediaState, current_position
from wisp.tools.base import Risk, ToolContext, ToolError
from wisp.tools.builtin import system as system_tools

# The Night Light "off" blob read from this PC's registry (2026-10-13); 41 bytes.
OFF_BLOB = bytes.fromhex(
    "43 42 01 00 0a 02 01 00 2a 06 cb e1 9d d6 06 2a 2b 0e 13 43 42 01 00 d0 0a 02 c6 14 af b7"
    " d5 ea 80 e2 d5 ee 01 00 00 00 00")
NOW = 1_800_000_000


def _tool(name: str):
    return next(t for t in system_tools.tools() if t.name == name)


def _risk(name: str, args: dict) -> Risk:
    tool = _tool(name)
    return tool.risk_fn(args) if tool.risk_fn else tool.risk


# ----- Night Light blob (UNDOCUMENTED, D-030) ----------------------------------------------------
def test_parse_night_light_off_blob():
    assert parse_night_light(OFF_BLOB) is False


def test_toggle_on_then_off_round_trips():
    on = toggle_night_light_blob(OFF_BLOB, True, now=NOW)
    assert parse_night_light(on) is True
    assert len(on) == len(OFF_BLOB) + 2 and on[23:25] == b"\x10\x00"
    assert controls._decode_varint(on[10:15]) == NOW
    off = toggle_night_light_blob(on, False, now=NOW + 5)
    assert parse_night_light(off) is False
    assert off[:10] == OFF_BLOB[:10] and off[15:] == OFF_BLOB[15:]  # only the stamp changed
    assert controls._decode_varint(off[10:15]) == NOW + 5


def test_toggle_to_same_state_only_refreshes_stamp():
    same = toggle_night_light_blob(OFF_BLOB, False, now=NOW)
    assert len(same) == len(OFF_BLOB) and parse_night_light(same) is False
    assert controls._decode_varint(same[10:15]) == NOW


@pytest.mark.parametrize("blob", [b"", b"XX" + OFF_BLOB[2:],
                                  OFF_BLOB[:18] + b"\x99" + OFF_BLOB[19:], OFF_BLOB[:20]])
def test_unknown_layout_is_refused(blob):
    with pytest.raises(ValueError):
        parse_night_light(blob)
    with pytest.raises(ValueError):
        toggle_night_light_blob(blob, True)


def test_varint_round_trip():
    for value in (0, 1, 127, 128, 300, NOW, 2**34 - 1):
        assert controls._decode_varint(controls._encode_varint(value)) == value


# ----- media position ----------------------------------------------------------------------------
def test_current_position_adds_elapsed_only_while_playing():
    now = datetime(2026, 10, 13, 12, 0, 10, tzinfo=UTC)
    snap = now - timedelta(seconds=10)
    assert current_position(30.0, snap, True, now) == pytest.approx(40.0)
    assert current_position(30.0, snap, False, now) == 30.0
    assert current_position(30.0, None, True, now) == 30.0
    naive = snap.replace(tzinfo=None)  # treated as UTC
    assert current_position(30.0, naive, True, now) == pytest.approx(40.0)
    future = now + timedelta(seconds=5)  # clock skew never moves backwards
    assert current_position(30.0, future, True, now) == 30.0


def test_media_state_progress():
    assert MediaState(True, position=30, duration=120).progress == 0.25
    assert MediaState(True, position=500, duration=120).progress == 1.0
    assert MediaState(True, position=30, duration=0).progress == 0.0


# ----- tool risk tiers ---------------------------------------------------------------------------
def test_wifi_off_needs_confirmation_and_says_why():
    assert _risk("toggle_setting", {"setting": "wifi", "on": False}) == Risk.CONFIRM
    assert _risk("toggle_setting", {"setting": "wifi", "on": True}) == Risk.SAFE
    assert _risk("toggle_setting", {"setting": "bluetooth", "on": False}) == Risk.SAFE
    assert _risk("toggle_setting", {"setting": "night_light", "on": True}) == Risk.SAFE
    summary = _tool("toggle_setting").describe({"setting": "wifi", "on": False})
    assert "disconnects Wisp" in summary


def test_power_actions_except_lock_need_confirmation():
    assert _risk("power", {"action": "lock"}) == Risk.SAFE
    for action in ("sleep", "restart", "shutdown"):
        assert _risk("power", {"action": action}) == Risk.CONFIRM
    assert _tool("power").describe({"action": "restart"}) == "restart the PC"


def test_clipboard_tools_flags():
    assert _tool("clipboard_history").untrusted_output is True
    assert _tool("clipboard_history").schedulable is False
    assert _tool("copy_to_clipboard").escalate_when_tainted is True


# ----- tool logic with fake controls -------------------------------------------------------------
class FakeControls:
    def __init__(self):
        self.level, self.muted, self.bright = 40, False, 70
        self.default = "spk"
        self.devices = [OutputDevice("spk", "Speakers (Realtek Audio)", True),
                        OutputDevice("hp", "Headphones (WH-1000XM5)", False)]

    def volume(self):
        return self.level, self.muted

    def set_volume(self, level):
        self.level = max(0, min(100, level))
        return self.level

    def set_mute(self, muted):
        self.muted = muted

    def brightness(self):
        return self.bright

    def set_brightness(self, level):
        self.bright = max(0, min(100, level))
        return self.bright

    def output_devices(self):
        return self.devices

    def set_default_output(self, device_id):
        self.default = device_id


@pytest.fixture
def fake(monkeypatch):
    fake = FakeControls()
    for name in ("volume", "set_volume", "set_mute", "brightness", "set_brightness",
                 "output_devices", "set_default_output"):
        monkeypatch.setattr(controls, name, getattr(fake, name))
    return fake


CTX = ToolContext("voice", SimpleNamespace())


def test_volume_tool(fake):
    assert system_tools.volume_tool(CTX, {"action": "get"}) == {"volume": 40, "muted": False}
    assert system_tools.volume_tool(CTX, {"action": "up"}) == {"volume": 50}
    assert system_tools.volume_tool(CTX, {"action": "down", "level": 70}) == {"volume": 0}
    assert system_tools.volume_tool(CTX, {"action": "set", "level": 25}) == {"volume": 25}
    system_tools.volume_tool(CTX, {"action": "mute"})
    assert fake.muted is True


def test_brightness_tool(fake, monkeypatch):
    assert system_tools.brightness_tool(CTX, {"action": "up", "level": 50}) == {"brightness": 100}
    monkeypatch.setattr(controls, "brightness", lambda: None)
    with pytest.raises(ToolError, match="external monitors"):
        system_tools.brightness_tool(CTX, {"action": "get"})


def test_output_device_lists_and_fuzzy_switches(fake):
    listed = system_tools.output_device_tool(CTX, {})
    assert listed["default"] == "Speakers (Realtek Audio)" and len(listed["devices"]) == 2
    assert system_tools.output_device_tool(CTX, {"name": "headphones"}) == {
        "default_output": "Headphones (WH-1000XM5)"}
    assert fake.default == "hp"
    with pytest.raises(ToolError, match="No output device"):
        system_tools.output_device_tool(CTX, {"name": "zzzz qqqq"})


async def test_toggle_tool_reports_unavailable_with_settings_page(monkeypatch):
    def refuse(enabled):
        raise ControlUnavailable("Night Light can't be switched directly on this PC.",
                                 controls.SETTINGS_PAGES["night_light"])

    monkeypatch.setattr(controls, "set_night_light", refuse)
    with pytest.raises(ToolError, match="ms-settings:nightlight"):
        await system_tools.toggle_tool(CTX, {"setting": "night_light", "on": True})


async def test_toggle_tool_radio_outcomes(monkeypatch):
    from wisp.system import radios

    outcomes = iter(["ok", "denied", "missing"])

    async def fake_set_state(kind, enabled):
        return next(outcomes)

    monkeypatch.setattr(radios, "set_state", fake_set_state)
    assert await system_tools.toggle_tool(CTX, {"setting": "bluetooth", "on": True}) == {
        "bluetooth": "on"}
    with pytest.raises(ToolError, match="didn't allow"):
        await system_tools.toggle_tool(CTX, {"setting": "bluetooth", "on": False})
    with pytest.raises(ToolError, match="no wifi radio"):
        await system_tools.toggle_tool(CTX, {"setting": "wifi", "on": True})


async def test_media_tool_status_and_command():
    import concurrent.futures

    class Watcher:
        state = MediaState(True, "Song", "Band", "Spotify", True, 61.4, 200.0)

        def command(self, action):
            future = concurrent.futures.Future()
            future.set_result(action != "next")
            return future

    ctx = ToolContext("voice", SimpleNamespace(media=Watcher()))
    status = await system_tools.media_tool(ctx, {"action": "status"})
    assert status == {"title": "Song", "artist": "Band", "playing": True, "position_s": 61,
                      "duration_s": 200}
    assert await system_tools.media_tool(ctx, {"action": "pause"}) == {"done": "pause"}
    with pytest.raises(ToolError):
        await system_tools.media_tool(ctx, {"action": "next"})
