"""File tools (skill group "files"): open, recent, search, delete to Recycle Bin."""

from __future__ import annotations

from wisp.tools.base import Risk, Tool, ToolContext, ToolError, integer, obj, string
from wisp.winapi import files as fs


def _existing(text: str):
    path = fs.resolve_path(text)
    if not path.exists():
        raise ToolError(f"{path} doesn't exist.")
    return path


def open_path(ctx: ToolContext, args: dict) -> dict:
    path = _existing(args["path"])
    fs.open_path(path)
    return {"opened": str(path), "kind": "folder" if path.is_dir() else "file"}


def find_recent_files(ctx: ToolContext, args: dict) -> dict:
    limit = max(1, min(args.get("limit", 10), 30))
    return {"files": [h.as_dict() for h in fs.recent_files(args.get("query"), limit)]}


def search_files(ctx: ToolContext, args: dict) -> dict:
    roots = None
    if args.get("folder"):
        roots = [_existing(args["folder"])]
    hits = fs.search_files(args["query"], roots, limit=max(1, min(args.get("limit", 10), 30)))
    return {"files": [h.as_dict() for h in hits]}


def delete_to_recycle_bin(ctx: ToolContext, args: dict) -> dict:
    path = fs.resolve_path(args["path"])
    reason = fs.protected_reason(path)
    if reason:
        raise ToolError(reason)
    fs.recycle(path)
    return {"recycled": str(path), "undo": "Restore it from the Recycle Bin if needed."}


def _open_risk(args: dict) -> Risk:
    path = fs.resolve_path(args.get("path", ""))
    return Risk.CONFIRM if fs.is_executable(path) else Risk.SAFE


def tools() -> list[Tool]:
    return [
        Tool("open_path", "Open a file or folder with its default app. Accepts full paths or "
             "folder names like 'downloads'. Programs and scripts need confirmation.",
             obj({"path": string("Path or known folder name")}, ["path"]), open_path, "files",
             risk_fn=_open_risk, escalate_when_tainted=True,
             summary=lambda a: f"open {a.get('path')}"),
        Tool("find_recent_files", "Recently used files, newest first, optionally filtered.",
             obj({"query": string("Part of the file name"), "limit": integer("Max results")}),
             find_recent_files, "files", untrusted_output=True),
        Tool("search_files", "Find files by name in Desktop, Documents, Downloads, Pictures, "
             "Music and Videos (or one folder).",
             obj({"query": string("Part of the name"), "folder": string("Optional folder"),
                  "limit": integer("Max results")}, ["query"]),
             search_files, "files", untrusted_output=True),
        Tool("delete_to_recycle_bin", "Move a file or folder to the Recycle Bin (never permanent "
             "delete). Needs confirmation.",
             obj({"path": string("Full path of the item")}, ["path"]),
             delete_to_recycle_bin, "files", risk=Risk.CONFIRM,
             summary=lambda a: f"move {a.get('path')} to the Recycle Bin"),
    ]
