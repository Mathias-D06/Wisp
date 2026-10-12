"""Scheduling tools (skill group "schedule"): routines that replay resolved tool calls.

The model turns "every morning at 9, open Unity and Spotify" into one schedule_task call whose
steps are concrete tool calls ([open_app Unity, open_app Spotify]). Those calls are validated now
and replayed later without asking the model again. A step can instead be a ``prompt`` for things
that need the assistant at run time.
"""

from __future__ import annotations

import json
from datetime import datetime

from wisp.scheduling.spec import REPEATS, ScheduleError, parse_schedule
from wisp.tools.base import (
    Risk,
    Tool,
    ToolContext,
    ToolError,
    array,
    boolean,
    integer,
    obj,
    string,
)
from wisp.tools.schema import validate_args

SCHEDULE_TOOLS = {"schedule_task", "list_scheduled_tasks", "update_scheduled_task",
                  "delete_scheduled_task", "run_scheduled_task_now", "confirm_action"}


def resolve_steps(registry, settings, raw_steps: list[dict], prompt: str | None) -> list[dict]:
    """Validate the model's steps against real tools; return storable steps."""
    steps: list[dict] = []
    for index, raw in enumerate(raw_steps or [], 1):
        name = raw.get("tool", "")
        tool = registry.get(name)
        if tool is None:
            raise ToolError(f"Step {index}: unknown tool '{name}'.")
        if name in SCHEDULE_TOOLS or not tool.schedulable:
            raise ToolError(f"Step {index}: {name} can't be part of a scheduled task.")
        if not registry.is_offered(tool, settings):
            raise ToolError(f"Step {index}: {name} is switched off in Settings.")
        try:
            args = json.loads(raw.get("args_json") or "{}")
        except ValueError as exc:
            raise ToolError(f"Step {index}: args_json is not valid JSON.") from exc
        if not isinstance(args, dict):
            raise ToolError(f"Step {index}: args_json must be a JSON object.")
        steps.append({"tool": name, "args": validate_args(tool.parameters, args)})
    if prompt and prompt.strip():
        steps.append({"prompt": prompt.strip()[:1000]})
    if not steps:
        raise ToolError("A scheduled task needs at least one step or a prompt.")
    return steps


def steps_need_confirmation(registry, steps: list[dict]) -> bool:
    for step in steps:
        tool = registry.get(step.get("tool", ""))
        if tool is None or not isinstance(step.get("args"), dict):
            continue
        tier = tool.risk_fn(step["args"]) if tool.risk_fn else tool.risk
        if tier == Risk.CONFIRM or (tool.risk == Risk.DISABLED
                                    and tool.tier_when_enabled == Risk.CONFIRM):
            return True
    return False


def _now() -> datetime:
    return datetime.now().astimezone()


def _schedule(args: dict):
    try:
        return parse_schedule(args, _now())
    except ScheduleError as exc:
        raise ToolError(str(exc)) from exc


def _find(ctx: ToolContext, query: str):
    task = ctx.services.tasks.find(query)
    if task is None:
        raise ToolError(f"No scheduled task matches '{query}'.")
    return task


def tools(registry) -> list[Tool]:
    def schedule_task(ctx: ToolContext, args: dict) -> dict:
        settings = ctx.services.settings.peek()
        steps = resolve_steps(registry, settings, args.get("steps", []), args.get("prompt"))
        schedule = _schedule(args)
        task = ctx.services.tasks.add(args["title"], schedule, steps)
        ctx.services.scheduler.schedule(task)
        next_run = ctx.services.scheduler.next_run(task.id)
        return {"scheduled": task.as_dict(next_run)}

    def list_scheduled_tasks(ctx: ToolContext, args: dict) -> dict:
        scheduler = ctx.services.scheduler
        return {"tasks": [t.as_dict(scheduler.next_run(t.id)) for t in ctx.services.tasks.list()]}

    def update_scheduled_task(ctx: ToolContext, args: dict) -> dict:
        task = _find(ctx, args["task"])
        schedule = None
        if any(args.get(k) for k in ("when", "repeat", "time", "days", "day_of_month")):
            repeat = args.get("repeat") or task.schedule.repeat
            when = args.get("when") or task.schedule.at
            if repeat == "none" and args.get("time") and not args.get("when") and when:
                # "Move it to 3 pm": keep the original date, change only the time.
                try:
                    hour, minute = (int(part) for part in args["time"].split(":"))
                    when = datetime.fromisoformat(when).replace(hour=hour, minute=minute)
                except ValueError as exc:
                    raise ToolError("time must look like 15:00.") from exc
                when = when.isoformat()
            keep_time = None if args.get("when") else task.schedule.time
            merged = {"repeat": repeat,
                      "time": args.get("time") or keep_time,
                      "days": args.get("days") or task.schedule.days,
                      "day_of_month": args.get("day_of_month") or task.schedule.day_of_month,
                      "when": when}
            schedule = _schedule(merged)
        updated = ctx.services.tasks.update(task.id, title=args.get("title"), schedule=schedule,
                                            enabled=args.get("enabled"))
        ctx.services.scheduler.schedule(updated)
        return {"updated": updated.as_dict(ctx.services.scheduler.next_run(updated.id))}

    def delete_scheduled_task(ctx: ToolContext, args: dict) -> dict:
        task = _find(ctx, args["task"])
        ctx.services.scheduler.unschedule(task.id)
        ctx.services.tasks.delete(task.id)
        return {"deleted": task.title}

    def run_scheduled_task_now(ctx: ToolContext, args: dict) -> dict:
        task = _find(ctx, args["task"])
        ctx.services.scheduler.run_now(task.id)
        return {"running": task.title}

    def risk(args: dict) -> Risk:
        try:
            steps = [{"tool": s.get("tool", ""), "args": json.loads(s.get("args_json") or "{}")}
                     for s in args.get("steps", [])]
        except (ValueError, AttributeError, TypeError):
            return Risk.SAFE  # malformed steps are rejected by the handler before anything runs
        return Risk.CONFIRM if steps_need_confirmation(registry, steps) else Risk.SAFE

    step = obj({"tool": string("Tool name, e.g. open_app"),
                "args_json": string('Tool arguments as JSON, e.g. {"name": "Spotify"}')},
               ["tool"])
    timing = {
        "when": string("ISO 8601 local date-time: the run time for one-off tasks, or the first "
                       "occurrence for repeating ones"),
        "repeat": string("How often", REPEATS),
        "time": string("HH:MM for repeating tasks"),
        "days": array(string("Day", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]),
                      "Days for weekly tasks"),
        "day_of_month": integer("Day for monthly tasks"),
    }
    which = string("Task id or title")
    return [
        Tool("schedule_task",
             "Schedule a one-off or repeating task. Put the concrete tool calls in steps "
             "(e.g. open_app, web_search); use prompt only for things needing you at run time. "
             "Call get_current_time first.",
             obj({"title": string("Short title"), **timing,
                  "steps": array(step, "Tool calls to run, in order"),
                  "prompt": string("Optional instruction for you at run time")},
                 ["title"]),
             schedule_task, "schedule", risk_fn=risk, schedulable=False,
             summary=lambda a: f"schedule '{a.get('title')}'"),
        Tool("list_scheduled_tasks", "List scheduled tasks with their next run.", obj(),
             list_scheduled_tasks, "schedule", schedulable=False),
        Tool("update_scheduled_task", "Change a scheduled task's title, timing or on/off state.",
             obj({"task": which, "title": string("New title"), **timing,
                  "enabled": boolean("Turn on or off")}, ["task"]),
             update_scheduled_task, "schedule", schedulable=False),
        Tool("delete_scheduled_task", "Delete a scheduled task. Needs confirmation.",
             obj({"task": which}, ["task"]), delete_scheduled_task, "schedule",
             risk=Risk.CONFIRM, schedulable=False,
             summary=lambda a: f"delete the scheduled task '{a.get('task')}'"),
        Tool("run_scheduled_task_now", "Run a scheduled task immediately.",
             obj({"task": which}, ["task"]), run_scheduled_task_now, "schedule",
             schedulable=False),
    ]
