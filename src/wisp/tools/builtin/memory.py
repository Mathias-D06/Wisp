"""Memory tools (skill group "memory"): remember, recall, forget.

remember and forget ask for confirmation right after untrusted content was read (D-012), so a web
page or document can't plant or erase facts that would shape later sessions (D-032).
"""

from __future__ import annotations

from wisp.tools.base import Tool, ToolContext, ToolError, boolean, integer, obj, string


def _store(ctx: ToolContext):
    return ctx.services.memory


def remember(ctx: ToolContext, args: dict) -> dict:
    replaced = None
    if args.get("replaces"):
        old = _store(ctx).find(args["replaces"])
        if old is None:
            raise ToolError(f"No memory matches '{args['replaces']}' to replace.")
        replaced = old.text
    try:
        memory = _store(ctx).add(args["fact"], bool(args.get("pinned")))
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    if replaced is not None and old.id != memory.id:
        _store(ctx).delete(old.id)
    result = {"remembered": memory.text}
    if replaced is not None:
        result["replaced"] = replaced
    return result


def recall(ctx: ToolContext, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit") or 5), 20))
    matches = _store(ctx).search(args["query"], limit)
    _store(ctx).mark_used([m.id for m in matches])
    if not matches:
        return {"memories": [], "note": "Nothing remembered about that."}
    return {"memories": [m.as_dict() for m in matches]}


def forget(ctx: ToolContext, args: dict) -> dict:
    memory = _store(ctx).find(args["memory"])
    if memory is None:
        raise ToolError(f"No memory matches '{args['memory']}'.")
    _store(ctx).delete(memory.id)
    return {"forgot": memory.text}


def tools() -> list[Tool]:
    return [
        Tool("remember", "Save a short fact about the user for future conversations (only when "
             "the user asks you to remember it). Use replaces to update an older fact.",
             obj({"fact": string("The fact, in one short sentence"),
                  "pinned": boolean("Always include it at the start of conversations"),
                  "replaces": string("Id or words of an older memory this one replaces")},
                 ["fact"]),
             remember, "memory", escalate_when_tainted=True,
             summary=lambda a: f"remember '{a.get('fact', '')[:80]}'"),
        Tool("recall", "Search what the user asked you to remember.",
             obj({"query": string("Words to search for"), "limit": integer("Max results")},
                 ["query"]),
             recall, "memory", schedulable=False),
        Tool("forget", "Delete one remembered fact.",
             obj({"memory": string("The memory's id or words from it")}, ["memory"]),
             forget, "memory", escalate_when_tainted=True,
             summary=lambda a: f"forget '{a.get('memory', '')[:80]}'"),
    ]
