"""Unit tests: argument validation, safety tiers, confirmations."""

from __future__ import annotations

import pytest

from wisp.settings import Settings
from wisp.tools.base import Origin, Risk, Tool, ToolError, array, boolean, integer, obj, string
from wisp.tools.confirm import ConfirmationManager, classify_reply
from wisp.tools.registry import ToolRegistry
from wisp.tools.safety import SafetyPolicy, TaintTracker
from wisp.tools.schema import validate_args

SCHEMA = obj(
    {
        "name": string("n"),
        "count": integer("c"),
        "flag": boolean("f"),
        "site": string("s", ["google", "youtube"]),
        "items": array(string("i"), "list"),
    },
    ["name"],
)


def make_tool(name="t", group="apps", risk=Risk.SAFE, **kw) -> Tool:
    return Tool(name=name, description="d", parameters=obj(), handler=lambda c, a: "ok",
                group=group, risk=risk, **kw)


# ----- schema ------------------------------------------------------------------------------
def test_validate_cleans_and_coerces():
    out = validate_args(SCHEMA, {"name": "x", "count": 3.0, "flag": "true", "extra": 1})
    assert out == {"name": "x", "count": 3, "flag": True}


def test_validate_reports_problems():
    with pytest.raises(ToolError) as err:
        validate_args(SCHEMA, {"count": "many", "site": "bing", "items": "a"})
    text = str(err.value)
    assert "name is required" in text
    assert "count must be a whole number" in text
    assert "site must be one of" in text
    assert "items must be a list" in text


def test_validate_rejects_bool_as_int():
    with pytest.raises(ToolError):
        validate_args(SCHEMA, {"name": "x", "count": True})


# ----- safety ------------------------------------------------------------------------------
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def policy(settings=None, clock=None):
    settings = settings or Settings()
    taint = TaintTracker(lambda: settings.safety.taint_minutes, clock or Clock())
    return SafetyPolicy(lambda: settings, taint), settings


def test_safe_tool_allowed():
    p, _ = policy()
    assert p.decide(make_tool(), {}, Origin.VOICE).action == "allow"


def test_confirm_tier_asks():
    p, _ = policy()
    decision = p.decide(make_tool(risk=Risk.CONFIRM), {}, Origin.VOICE)
    assert decision.action == "confirm"


def test_disabled_tier_denied_until_toggle():
    p, settings = policy()
    settings.loadout.skills.append("terminal")
    tool = make_tool("run_command", group="terminal", risk=Risk.DISABLED,
                     enabled_by="allow_terminal")
    assert p.decide(tool, {}, Origin.VOICE).action == "deny"
    settings.safety.allow_terminal = True
    assert p.decide(tool, {}, Origin.VOICE).action == "confirm"  # tier_when_enabled


def test_raw_input_enabled_is_safe_but_escalates_when_tainted():
    clock = Clock()
    p, settings = policy(clock=clock)
    settings.loadout.skills.append("input")
    settings.safety.allow_raw_input = True
    tool = make_tool("mouse_click_at", group="input", risk=Risk.DISABLED,
                     enabled_by="allow_raw_input", tier_when_enabled=Risk.SAFE,
                     escalate_when_tainted=True)
    assert p.decide(tool, {}, Origin.VOICE).action == "allow"
    p.taint.mark("look_at_screen")
    assert p.decide(tool, {}, Origin.VOICE).action == "confirm"
    clock.t += settings.safety.taint_minutes * 60 + 1
    assert p.decide(tool, {}, Origin.VOICE).action == "allow"


def test_auto_approve_ignored_when_tainted_and_for_schedules():
    p, settings = policy()
    tool = make_tool("close_window", risk=Risk.CONFIRM)
    settings.safety.auto_approve = ["close_window"]
    assert p.decide(tool, {}, Origin.VOICE).action == "allow"
    assert p.decide(tool, {}, Origin.SCHEDULE).action == "confirm"
    p.taint.mark("read_file")
    assert p.decide(tool, {}, Origin.VOICE).action == "confirm"


def test_risk_fn_escalates_dangerous_args():
    p, _ = policy()
    tool = make_tool("click_element", risk_fn=lambda a: Risk.CONFIRM if a.get("name") == "Buy"
                     else Risk.SAFE)
    assert p.decide(tool, {"name": "Settings"}, Origin.VOICE).action == "allow"
    assert p.decide(tool, {"name": "Buy"}, Origin.VOICE).action == "confirm"


def test_skill_switched_off_denies():
    p, settings = policy()
    settings.loadout.skills.remove("apps")
    assert p.decide(make_tool(), {}, Origin.VOICE).action == "deny"


def test_registry_offers_only_enabled():
    registry = ToolRegistry()
    registry.register(make_tool("open_app"))
    registry.register(make_tool("run_command", group="terminal", risk=Risk.DISABLED,
                                enabled_by="allow_terminal"))
    settings = Settings()
    names = {d["name"] for d in registry.declarations(settings)}
    assert names == {"open_app"}
    settings.loadout.skills.append("terminal")
    settings.safety.allow_terminal = True
    names = {d["name"] for d in registry.declarations(settings)}
    assert names == {"open_app", "run_command"}
    with pytest.raises(ValueError):
        registry.register(make_tool("open_app"))


# ----- confirmations -----------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("Yes.", "yes"), ("yeah do it", "yes"), ("Okay go ahead", "yes"), ("oui", "yes"),
    ("No.", "no"), ("no, cancel that", "no"), ("wait", "no"), ("yes, wait", "no"),
    ("what's the weather like today in London", None), ("", None),
    ("yes I think so but first tell me about the weather", None),
])
def test_classify_reply(text, expected):
    assert classify_reply(text) == expected


def test_utterance_applies_to_latest_pending_created_before_it():
    clock = Clock()
    manager = ConfirmationManager(clock=clock)
    first = manager.create("a", {}, "A", Origin.VOICE)
    clock.t += 1
    second = manager.create("b", {}, "B", Origin.VOICE)
    clock.t += 1
    resolved = manager.on_user_utterance("yes")
    assert resolved is second and second.state == "approved"
    assert first.state == "pending"
    assert second.evidence.startswith("voice")


def test_utterance_before_pending_does_not_count():
    clock = Clock()
    manager = ConfirmationManager(clock=clock)
    item = manager.create("a", {}, "A", Origin.VOICE)
    assert manager.on_user_utterance("yes", at=item.created - 5) is None
    assert item.state == "pending"


def test_schedule_items_not_resolved_by_voice():
    manager = ConfirmationManager(clock=Clock())
    item = manager.create("a", {}, "A", Origin.SCHEDULE)
    assert manager.on_user_utterance("yes") is None
    assert manager.approve_click(item.id)
    assert item.state == "approved"


def test_expiry():
    clock = Clock()
    manager = ConfirmationManager(ttl_seconds=10, clock=clock)
    item = manager.create("a", {}, "A", Origin.VOICE)
    clock.t += 11
    assert manager.pending() == []
    assert item.state == "expired"
    assert not manager.approve_click(item.id)
