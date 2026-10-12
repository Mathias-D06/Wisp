"""App launching tools (skill group "apps")."""

from __future__ import annotations

from wisp.tools.base import Tool, ToolContext, ToolError, integer, obj, string

MIN_SCORE = 70


def open_app(ctx: ToolContext, args: dict) -> dict:
    index = ctx.services.app_index
    if index.count() == 0:
        index.refresh()
    query = args["name"].strip()
    matches = index.search(query, limit=3)
    if not matches or matches[0][1] < MIN_SCORE:
        raise ToolError(f"I couldn't find an installed app called '{query}'.")
    best, best_score = matches[0]
    exact = best.name.lower() == query.lower()
    rivals = [m for m, s in matches[1:]
              if s >= best_score - 3 and m.name.lower() != best.name.lower()]
    if rivals and not exact:
        return {"ambiguous": True, "options": [best.name] + [r.name for r in rivals],
                "next": "Ask the user which one they mean, then call open_app with that name."}
    index.launch(best)
    return {"opened": best.name}


def find_apps(ctx: ToolContext, args: dict) -> dict:
    index = ctx.services.app_index
    if index.count() == 0:
        index.refresh()
    limit = max(1, min(args.get("limit", 8), 20))
    matches = [(e.name, round(s)) for e, s in index.search(args["query"], limit)
               if s >= MIN_SCORE - 10]
    return {"apps": [name for name, _ in matches]}


def tools() -> list[Tool]:
    return [
        Tool(
            name="open_app",
            description="Open an installed app by name (fuzzy match, e.g. 'spotify', 'word').",
            parameters=obj({"name": string("App name as the user said it")}, ["name"]),
            handler=open_app,
            group="apps",
            summary=lambda a: f"open {a.get('name')}",
        ),
        Tool(
            name="find_apps",
            description="List installed apps whose names match a query.",
            parameters=obj({"query": string("Part of an app name"), "limit": integer("Max")},
                           ["query"]),
            handler=find_apps,
            group="apps",
        ),
    ]
