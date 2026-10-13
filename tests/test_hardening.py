"""Phase 9 (F11/F12): terminal and raw-input tools behind Safety toggles, auto-approval limits,
UAC/secure-desktop refusals, action log retention, crash logging."""

from __future__ import annotations

import logging
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from wisp.settings import NEVER_AUTO_APPROVE, Settings, validate
from wisp.tools.base import Origin, Risk, ToolContext, ToolError
from wisp.tools.builtin import raw_input, terminal
from wisp.tools.registry import ToolRegistry
from wisp.tools.safety import SafetyPolicy, TaintTracker
from wisp.winapi import windows as win
from wisp.winapi.screen import Capture
from wisp.winapi.uia import ELEVATED_MESSAGE, SECURE_DESKTOP_MESSAGE


def _registry() -> ToolRegistry:
    from wisp.tools.builtin import windows as window_tools

    registry = ToolRegistry()
    registry.register_all(terminal.tools() + raw_input.tools() + window_tools.tools())
    return registry


def _policy(settings: Settings, taint: TaintTracker | None = None) -> SafetyPolicy:
    return SafetyPolicy(lambda: settings, taint or TaintTracker(lambda: 5))


# ----- F12.3: off by default, behind a Settings toggle --------------------------------------------
def test_terminal_and_raw_input_off_by_default():
    settings = Settings()
    registry = _registry()
    offered = {d["name"] for d in registry.declarations(settings)}
    assert not offered & {"run_command", "mouse_click", "press_keys", "type_text",
                          "mouse_scroll"}
    policy = _policy(settings)
    for name in ("run_command", "mouse_click", "press_keys"):
        decision = policy.decide(registry.get(name), {"command": "dir", "x": 1, "y": 1,
                                                      "keys": "f5"}, Origin.VOICE)
        assert decision.action == "deny"


def test_terminal_needs_toggle_and_skill_then_always_asks():
    settings = Settings()
    registry = _registry()
    run = registry.get("run_command")
    settings.safety.allow_terminal = True
    assert _policy(settings).decide(run, {"command": "dir"}, Origin.VOICE).action == "deny"
    settings.loadout.skills.append("terminal")
    assert "run_command" in {d["name"] for d in registry.declarations(settings)}
    settings.safety.auto_approve = ["run_command"]  # hand-edited settings.json
    decision = _policy(settings).decide(run, {"command": "dir"}, Origin.VOICE)
    assert decision.action == "confirm"
    assert any("always ask" in p for p in validate(settings))


def test_raw_input_tiers_when_enabled():
    settings = Settings()
    settings.safety.allow_raw_input = True
    settings.loadout.skills.append("input")
    registry = _registry()
    policy = _policy(settings)

    def action(name, args):
        return policy.decide(registry.get(name), args, Origin.VOICE).action

    assert action("mouse_click", {"x": 5, "y": 5}) == "confirm"
    assert action("press_keys", {"keys": "ctrl+t"}) == "allow"
    assert action("press_keys", {"keys": "Enter"}) == "confirm"
    assert action("press_keys", {"keys": "alt+F4"}) == "confirm"
    assert action("press_keys", {"keys": "win+r"}) == "confirm"
    assert action("press_keys", {"keys": "ctrl+nonsense"}) == "confirm"
    assert action("type_text", {"text": "hello"}) == "allow"
    assert action("type_text", {"text": "rm -rf\n"}) == "confirm"
    assert action("mouse_scroll", {"clicks": -3}) == "allow"


def test_auto_approve_limits():
    settings = Settings()
    registry = _registry()
    close = registry.get("close_window")
    taint = TaintTracker(lambda: 5)
    policy = _policy(settings, taint)
    settings.safety.auto_approve = ["close_window"]
    assert policy.decide(close, {"name": "Notepad"}, Origin.VOICE).action == "allow"
    assert policy.decide(close, {"name": "Notepad"}, Origin.SCHEDULE).action == "confirm"
    taint.mark("look_at_screen")  # F12.4: after untrusted content, confirm-tier always asks
    assert policy.decide(close, {"name": "Notepad"}, Origin.VOICE).action == "confirm"
    assert {"run_command", "mouse_click", "power", "delete_to_recycle_bin",
            "click_element"} <= NEVER_AUTO_APPROVE


# ----- terminal tool (real PowerShell, harmless commands) ----------------------------------------
CTX = ToolContext(Origin.VOICE, SimpleNamespace())


@pytest.mark.windows
def test_run_command_output_and_exit_code(tmp_path):
    result = terminal.run_command(CTX, {"command": "Write-Output 'héllo'; 2 + 3",
                                        "folder": str(tmp_path)})
    assert result["exit_code"] == 0 and result["output"].split("\n") == ["héllo", "5"]
    failed = terminal.run_command(CTX, {"command": "Get-Item 'Z:\\definitely\\missing'; exit 3"})
    assert failed["exit_code"] == 3 and failed["errors"]


@pytest.mark.windows
def test_run_command_timeout_kills_process():
    started = time.monotonic()
    result = terminal.run_command(CTX, {"command": "Start-Sleep -Seconds 30", "timeout_s": 2})
    assert result["timed_out"] is True and time.monotonic() - started < 20


def test_run_command_rejects_bad_input(tmp_path):
    with pytest.raises(ToolError):
        terminal.run_command(CTX, {"command": "  "})
    with pytest.raises(ToolError, match="Folder not found"):
        terminal.run_command(CTX, {"command": "dir", "folder": str(tmp_path / "nope")})


def test_terminal_args_and_clip():
    args = terminal.powershell_args("dir")
    assert args[:4] == ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive"]
    assert "-ExecutionPolicy" not in args and args[-1].endswith("dir")
    text = "a" * 3000 + "b" * 3000
    clipped = terminal.clip(text, 1000)
    assert clipped.startswith("a" * 500) and clipped.endswith("b" * 500)
    assert "5000 characters cut" in clipped
    assert terminal.tools()[0].untrusted_output is True


# ----- raw input tools (SendInput replaced by recorders) -----------------------------------------
@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(raw_input.winput, "mouse_click",
                        lambda x, y, button, double: calls.append(("click", x, y, button, double)))
    monkeypatch.setattr(raw_input.winput, "combo", lambda mods, key: calls.append(("combo", mods,
                                                                                    key)))
    monkeypatch.setattr(raw_input.winput, "type_text", lambda text: calls.append(("type", text)))
    monkeypatch.setattr(raw_input.winput, "mouse_wheel", lambda n: calls.append(("wheel", n)))
    monkeypatch.setattr(raw_input.winput, "release_held_modifiers", lambda: [])
    monkeypatch.setattr(win, "input_desktop_available", lambda: True)
    monkeypatch.setattr(win, "self_elevated", lambda: False)
    monkeypatch.setattr(win, "is_process_elevated", lambda pid: pid == 666)
    monkeypatch.setattr(raw_input.processes, "anti_cheat_running", lambda: [])
    app = win.WindowInfo(1, "Notepad", "notepad", 100, False, True)
    monkeypatch.setattr(win, "window_at", lambda x, y: app)
    monkeypatch.setattr(win, "foreground_window", lambda: app)
    return calls


def _ctx_with_capture(age_s: float = 0.0):
    # A 2560x1440 monitor at (1920, 0), sent to the model as a 1280x720 image.
    shot = Capture(b"", 2560, 1440, (1920, 0, 4480, 1440), (1280, 720))
    return ToolContext(Origin.VOICE, SimpleNamespace(last_capture=(shot,
                                                                  time.monotonic() - age_s)))


def test_capture_maps_image_pixels_to_screen():
    shot = Capture(b"", 2560, 1440, (1920, 0, 4480, 1440), (1280, 720))
    assert shot.to_screen(0, 0) == (1920, 0)
    assert shot.to_screen(640, 360) == (3200, 720)
    assert shot.to_screen(1280, 720) == (4479, 1439)  # clamped inside the monitor
    with pytest.raises(ValueError):
        shot.to_screen(1300, 10)


def test_mouse_click_maps_and_needs_a_recent_screenshot(sent):
    with pytest.raises(ToolError, match="look_at_screen first"):
        raw_input.mouse_click(ToolContext(Origin.VOICE, SimpleNamespace()), {"x": 1, "y": 1})
    with pytest.raises(ToolError, match="look_at_screen first"):
        raw_input.mouse_click(_ctx_with_capture(age_s=600), {"x": 1, "y": 1})
    result = raw_input.mouse_click(_ctx_with_capture(), {"x": 640, "y": 360, "double": True})
    assert sent == [("click", 3200, 720, "left", True)]
    assert result == {"clicked": [3200, 720], "window": "Notepad"}
    with pytest.raises(ToolError, match="outside"):
        raw_input.mouse_click(_ctx_with_capture(), {"x": 5000, "y": 1})


def test_keys_text_scroll(sent):
    assert raw_input.press_keys(CTX, {"keys": "Ctrl + Shift + T"}) == {"pressed": "ctrl+shift+t"}
    assert raw_input.type_text(CTX, {"text": "héllo"}) == {"typed_chars": 5}
    assert raw_input.mouse_scroll(CTX, {"clicks": -99}) == {"scrolled": -30}
    assert sent[0] == ("combo", [0x11, 0x10], ord("T"))
    assert sent[1:] == [("type", "héllo"), ("wheel", -30)]
    with pytest.raises(ToolError, match="Unknown key"):
        raw_input.press_keys(CTX, {"keys": "ctrl+banana"})
    with pytest.raises(ToolError):
        raw_input.type_text(CTX, {"text": "x" * 2001})


# ----- F12.6: never past UAC / secure desktop / elevated windows ---------------------------------
def test_refuses_secure_desktop_and_elevated_windows(sent, monkeypatch):
    elevated = win.WindowInfo(2, "Task Manager", "Taskmgr", 666, False, True)
    monkeypatch.setattr(win, "window_at", lambda x, y: elevated)
    monkeypatch.setattr(win, "foreground_window", lambda: elevated)
    with pytest.raises(ToolError) as info:
        raw_input.mouse_click(_ctx_with_capture(), {"x": 10, "y": 10})
    assert str(info.value) == ELEVATED_MESSAGE
    with pytest.raises(ToolError, match="administrator"):
        raw_input.press_keys(CTX, {"keys": "f5"})
    monkeypatch.setattr(win, "input_desktop_available", lambda: False)
    for call in (lambda: raw_input.type_text(CTX, {"text": "x"}),
                 lambda: raw_input.mouse_scroll(CTX, {"clicks": 1})):
        with pytest.raises(ToolError) as info:
            call()
        assert str(info.value) == SECURE_DESKTOP_MESSAGE
    assert sent == []  # nothing was injected


def test_anti_cheat_detection_and_fullscreen_rule():
    from wisp.winapi import processes

    assert processes.anti_cheat_running({"explorer", "beservice_x64", "vgc"}) == [
        "BattlEye", "Riot Vanguard"]
    assert processes.anti_cheat_running({"explorer", "code"}) == []
    monitor = (0, 0, 1920, 1080)
    assert raw_input.is_fullscreen((0, 0, 1920, 1080), monitor)
    assert raw_input.is_fullscreen((-1, -1, 1921, 1081), monitor)
    assert not raw_input.is_fullscreen((0, 0, 1920, 1040), monitor)  # taskbar visible
    assert not raw_input.is_fullscreen(None, monitor)


def test_refuses_fullscreen_window_while_anti_cheat_runs(sent, monkeypatch):
    monkeypatch.setattr(raw_input.processes, "anti_cheat_running", lambda: ["Easy Anti-Cheat"])
    monkeypatch.setattr(raw_input.screen, "monitor_at", lambda x, y: (0, 0, 1920, 1080))
    monkeypatch.setattr(win, "frame_bounds", lambda hwnd: (0, 0, 1920, 1080))
    with pytest.raises(ToolError, match="Easy Anti-Cheat is running"):
        raw_input.press_keys(CTX, {"keys": "f5"})
    monkeypatch.setattr(win, "frame_bounds", lambda hwnd: (100, 100, 900, 700))  # windowed app
    assert raw_input.press_keys(CTX, {"keys": "f5"}) == {"pressed": "f5"}


@pytest.mark.windows
def test_real_process_snapshot_lists_this_process():
    import os

    from wisp.winapi import processes

    names = processes.running_names()
    assert os.path.basename(sys.executable).lower().removesuffix(".exe") in names
    assert "explorer" in names or "system" in names


def test_look_at_screen_refuses_secure_desktop(monkeypatch):
    from wisp.tools.builtin import screen as screen_tools

    monkeypatch.setattr(screen_tools.win, "input_desktop_available", lambda: False)
    ctx = ToolContext(Origin.VOICE, SimpleNamespace(live=object()))
    with pytest.raises(ToolError) as info:
        screen_tools.look_at_screen(ctx, {})
    assert str(info.value) == SECURE_DESKTOP_MESSAGE


def test_instruction_states_the_limits():
    from datetime import datetime

    from wisp.live.config import system_instruction

    text = system_instruction(Settings(), [], datetime(2026, 10, 13))
    assert "UAC" in text and "lock screen" in text and "anti-cheat" in text


@pytest.mark.windows
def test_real_secure_desktop_probe_and_window_at():
    """Read-only: the normal desktop is the input desktop during tests; window_at answers."""
    from wisp.winapi import screen

    assert win.input_desktop_available() is True
    x, y = screen.cursor_position()
    found = win.window_at(x, y)
    assert found is None or found.pid > 0


# ----- F12.5: action log retention and redaction --------------------------------------------------
def test_action_log_prunes_and_redacts(db, monkeypatch):
    from wisp.stores import action_log as module
    from wisp.stores.action_log import ActionLog

    monkeypatch.setattr(module, "MAX_ROWS", 20)
    monkeypatch.setattr(module, "PRUNE_EVERY", 5)
    secret = "AIza" + "x" * 35
    log = ActionLog(db, lambda text: text.replace(secret, "[REDACTED]"))
    for n in range(42):
        log.record(origin="voice", tool="echo", args={"n": n, "key": secret}, decision="allow",
                   result={"ok": True}, ok=True)
    entries = log.recent(1000)
    assert 20 <= len(entries) <= 25 and '"n": 41' in entries[0].args
    assert all(secret not in e.args for e in entries)
    log.prune(3)
    assert len(log.recent()) == 3


# ----- crash logging ------------------------------------------------------------------------------
def test_uncaught_exceptions_reach_the_log(caplog):
    from wisp.logging_setup import install_exception_hooks

    saved = sys.excepthook, threading.excepthook
    try:
        install_exception_hooks()
        with caplog.at_level(logging.CRITICAL, logger="wisp.crash"):
            worker = threading.Thread(target=lambda: 1 / 0, name="probe-worker")
            worker.start()
            worker.join()
            try:
                raise ValueError("main boom")
            except ValueError:
                sys.excepthook(*sys.exc_info())
        messages = [r.getMessage() for r in caplog.records]
        assert "Uncaught exception in thread probe-worker" in messages
        assert "Uncaught exception" in messages
        assert any(r.exc_info and r.exc_info[0] is ZeroDivisionError for r in caplog.records)
    finally:
        sys.excepthook, threading.excepthook = saved


def test_raw_input_tools_never_scheduled_blind():
    tools = {t.name: t for t in raw_input.tools()}
    assert tools["mouse_click"].schedulable is False
    assert all(t.risk == Risk.DISABLED and t.enabled_by == "allow_raw_input"
               for t in tools.values())
