"""schedule_task and friends: step resolution, risk, CRUD by voice, replay without the model."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from tests.fakes import DirectUi, FakeLiveServer, tool_call, until
from wisp.live.session import LiveCallbacks, LiveSessionManager
from wisp.scheduling.tasks import TaskStore
from wisp.settings import Settings, SettingsStore
from wisp.stores.action_log import ActionLog
from wisp.tools.base import Origin, Risk, Tool, ToolContext, ToolError, obj, string
from wisp.tools.builtin import files as files_tools
from wisp.tools.builtin import schedule as schedule_tools
from wisp.tools.builtin import web as web_tools
from wisp.tools.confirm import ConfirmationManager
from wisp.tools.dispatcher import Dispatcher
from wisp.tools.registry import ToolRegistry
from wisp.tools.safety import SafetyPolicy, TaintTracker


class FakeScheduler:
    def __init__(self):
        self.scheduled, self.removed, self.ran = [], [], []

    def schedule(self, task):
        self.scheduled.append(task.id)

    def unschedule(self, task_id):
        self.removed.append(task_id)

    def next_run(self, task_id):
        return None

    def run_now(self, task_id):
        self.ran.append(task_id)


@pytest.fixture
def env(db, tmp_path):
    registry = ToolRegistry()
    opened: list[str] = []
    registry.register(Tool("open_app", "d", obj({"name": string("n")}, ["name"]),
                           lambda c, a: opened.append(a["name"]) or {"opened": a["name"]},
                           "apps"))
    registry.register_all(web_tools.tools())
    registry.register_all(files_tools.tools())
    registry.register_all(schedule_tools.tools(registry))
    services = SimpleNamespace(tasks=TaskStore(db), scheduler=FakeScheduler(),
                               settings=SettingsStore(tmp_path / "s.json"), ui=DirectUi())
    return SimpleNamespace(registry=registry, services=services, opened=opened,
                           ctx=ToolContext(Origin.VOICE, services))


def call(env, name, args):
    return env.registry.get(name).handler(env.ctx, args)


def step(tool, **args):
    return {"tool": tool, "args_json": json.dumps(args)}


def test_every_morning_routine_stores_resolved_calls(env):
    result = call(env, "schedule_task", {
        "title": "Morning apps", "repeat": "daily", "time": "09:00",
        "steps": [step("open_app", name="Unity"), step("open_app", name="Spotify")]})
    task = env.services.tasks.get(result["scheduled"]["id"])
    assert task.steps == [{"tool": "open_app", "args": {"name": "Unity"}},
                          {"tool": "open_app", "args": {"name": "Spotify"}}]
    assert task.schedule.describe() == "every day at 09:00"
    assert env.services.scheduler.scheduled == [task.id]


def test_amazon_one_off(env):
    result = call(env, "schedule_task", {
        "title": "Gift wrap search", "when": "2099-11-10T11:00",
        "steps": [step("web_search", query="gift wraps", site="amazon")]})
    assert result["scheduled"]["schedule"].startswith("once on Tue 10 Nov 2099 at 11:00")


@pytest.mark.parametrize("steps,message", [
    ([step("nope")], "unknown tool"),
    ([step("schedule_task", title="x")], "can't be part"),
    ([{"tool": "open_app", "args_json": "{bad"}], "not valid JSON"),
    ([step("open_app")], "name is required"),
    ([], "at least one step"),
])
def test_step_validation(env, steps, message):
    with pytest.raises(ToolError, match=message):
        call(env, "schedule_task", {"title": "t", "repeat": "daily", "time": "09:00",
                                    "steps": steps})


def test_disabled_skill_rejected(env):
    env.services.settings.update(lambda s: s.loadout.skills.remove("web"))
    with pytest.raises(ToolError, match="switched off"):
        call(env, "schedule_task", {"title": "t", "repeat": "daily", "time": "09:00",
                                    "steps": [step("web_search", query="x")]})


def test_routine_with_risky_step_needs_confirmation(env):
    tool = env.registry.get("schedule_task")
    safe = {"title": "t", "steps": [step("open_app", name="Notes")]}
    risky = {"title": "t", "steps": [step("delete_to_recycle_bin", path="C:/x.txt")]}
    assert tool.risk_fn(safe) == Risk.SAFE
    assert tool.risk_fn(risky) == Risk.CONFIRM


def test_prompt_step_list_update_delete_run(env):
    created = call(env, "schedule_task", {"title": "News", "repeat": "weekdays", "time": "08:00",
                                          "prompt": "Read me the top headline"})
    task_id = created["scheduled"]["id"]
    assert env.services.tasks.get(task_id).steps == [{"prompt": "Read me the top headline"}]
    assert call(env, "list_scheduled_tasks", {})["tasks"][0]["title"] == "News"
    updated = call(env, "update_scheduled_task", {"task": "news", "time": "07:30"})
    assert updated["updated"]["schedule"] == "weekdays at 07:30"
    off = call(env, "update_scheduled_task", {"task": task_id, "enabled": False})
    assert off["updated"]["enabled"] is False
    call(env, "run_scheduled_task_now", {"task": "News"})
    assert env.services.scheduler.ran == [task_id]
    assert call(env, "delete_scheduled_task", {"task": "News"}) == {"deleted": "News"}
    assert env.services.tasks.get(task_id) is None
    assert env.registry.get("delete_scheduled_task").risk == Risk.CONFIRM


def test_move_one_off_keeps_date(env):
    created = call(env, "schedule_task", {"title": "Call", "when": "2099-03-04T11:00",
                                          "steps": [step("open_app", name="Teams")]})
    moved = call(env, "update_scheduled_task", {"task": created["scheduled"]["id"],
                                                "time": "15:30"})
    assert moved["updated"]["schedule"] == "once on Wed 04 Mar 2099 at 15:30"


async def test_model_schedules_routine_then_it_replays_without_model(env, db):
    """Integration: a scripted Live session emits schedule_task; replay runs the stored steps
    through the dispatcher with Origin.SCHEDULE and no model involvement."""
    loop = asyncio.get_running_loop()
    settings = Settings()
    dispatcher = Dispatcher(env.registry, SafetyPolicy(lambda: settings, TaintTracker(lambda: 5)),
                            ConfirmationManager(), ActionLog(db), None, env.services)
    dispatcher.bind_loop(loop)
    server = FakeLiveServer()
    args = {"title": "Morning apps", "repeat": "daily", "time": "09:00",
            "steps": [step("open_app", name="Unity"), step("open_app", name="Spotify")]}

    def rule(session, kind, value):
        return [tool_call(("s1", "schedule_task", args))] if kind == "activity_end" else None

    server.rules.append(rule)
    manager = LiveSessionManager(loop, server, lambda h: SimpleNamespace(), dispatcher,
                                 LiveCallbacks(), has_key=lambda: True,
                                 idle_timeout_s=lambda: 3600, always_listening=lambda: False,
                                 tick_s=0.02)
    manager.begin_turn()
    manager.end_turn()
    await until(lambda: env.services.tasks.list())
    task = env.services.tasks.list()[0]
    assert env.opened == []  # nothing ran at scheduling time
    for stored in task.steps:
        result = await dispatcher.dispatch(stored["tool"], stored["args"], Origin.SCHEDULE)
        assert result["ok"]
    assert env.opened == ["Unity", "Spotify"]
    manager.disconnect()
    dispatcher.shutdown()
