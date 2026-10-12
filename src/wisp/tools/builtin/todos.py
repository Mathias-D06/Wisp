"""To-do tools (skill group "todos")."""

from __future__ import annotations

from datetime import datetime

from wisp.scheduling.spec import ScheduleError, parse_when
from wisp.tools.base import Risk, Tool, ToolContext, ToolError, boolean, obj, string


def _store(ctx: ToolContext):
    return ctx.services.todos


def _due(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return parse_when(text, datetime.now().astimezone().tzinfo)
    except ScheduleError as exc:
        raise ToolError(str(exc)) from exc


def _find(ctx: ToolContext, query: str):
    todo = _store(ctx).find(query)
    if todo is None:
        raise ToolError(f"No open to-do matches '{query}'.")
    return todo


def add_todo(ctx: ToolContext, args: dict) -> dict:
    todo = _store(ctx).add(args["text"], _due(args.get("due")), args.get("remind"))
    return {"added": todo.as_dict(), "reminder": todo.remind}


def list_todos(ctx: ToolContext, args: dict) -> dict:
    todos = _store(ctx).list(include_done=bool(args.get("include_done")))
    return {"todos": [t.as_dict() for t in todos[:30]]}


def complete_todo(ctx: ToolContext, args: dict) -> dict:
    todo = _find(ctx, args["todo"])
    _store(ctx).set_done(todo.id, True)
    return {"completed": todo.text}


def update_todo(ctx: ToolContext, args: dict) -> dict:
    todo = _find(ctx, args["todo"])
    _store(ctx).update(todo.id, text=args.get("text"), due_at=_due(args.get("due")))
    return {"updated": _store(ctx).get(todo.id).as_dict()}


def delete_todo(ctx: ToolContext, args: dict) -> dict:
    todo = _find(ctx, args["todo"])
    _store(ctx).delete(todo.id)
    return {"deleted": todo.text}


def tools() -> list[Tool]:
    which = string("The to-do's id or words from its text")
    due = string("Optional due date/time, ISO 8601 local (call get_current_time first)")
    return [
        Tool("add_todo", "Add a to-do, optionally with a due time and reminder.",
             obj({"text": string("What to do"), "due": due,
                  "remind": boolean("Remind at the due time (default yes if due given)")},
                 ["text"]),
             add_todo, "todos", summary=lambda a: f"add to-do '{a.get('text')}'"),
        Tool("list_todos", "List open to-dos (or all, including done).",
             obj({"include_done": boolean("Include completed")}), list_todos, "todos"),
        Tool("complete_todo", "Mark a to-do as done.", obj({"todo": which}, ["todo"]),
             complete_todo, "todos"),
        Tool("update_todo", "Change a to-do's text or due time.",
             obj({"todo": which, "text": string("New text"), "due": due}, ["todo"]),
             update_todo, "todos"),
        Tool("delete_todo", "Delete a to-do. Needs confirmation.", obj({"todo": which}, ["todo"]),
             delete_todo, "todos", risk=Risk.CONFIRM,
             summary=lambda a: f"delete the to-do '{a.get('todo')}'"),
    ]
