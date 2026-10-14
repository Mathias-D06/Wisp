"""Sharing tools (skill group "files", D-051): the Windows share sheet and the phone link.

* share_file opens the Windows share sheet (Nearby Sharing, Mail, Teams …) with a file; the
  person picks where it goes there, so nothing leaves the PC without their choice.
* send_to_phone opens the phone link with a QR code in the island; with a file, the phone can
  download it. It is confirm-tier: it puts a file on the home network (behind a one-time link).
* stop_phone_link closes it early (it also stops by itself after 10 minutes).

"this" means the files selected in the File Explorer window in front, or the newest file on the
shelf; "the file I just downloaded" means the newest file in Downloads (wisp.files.resolve).
"""

from __future__ import annotations

from pathlib import Path

from wisp.files.resolve import NotFound, explorer_selection, resolve
from wisp.tools.base import Risk, Tool, ToolContext, ToolError, obj, string
from wisp.winapi import windows as win

FILE_HELP = ("Which file: 'this' (selected in File Explorer, or the newest on the shelf), "
             "'latest download', 'shelf', a name or a full path")


def _files(ctx: ToolContext, text: str | None) -> list[Path]:
    services = ctx.services
    try:
        return resolve(text, services.finder, services.shelf,
                       lambda: explorer_selection(win.foreground_hwnd()))
    except NotFound as exc:
        raise ToolError(str(exc)) from exc


def share_file(ctx: ToolContext, args: dict) -> dict:
    paths = _files(ctx, args.get("file"))
    try:
        ctx.services.share_files(paths)
    except OSError as exc:
        raise ToolError(f"Windows couldn't open the share sheet ({exc}).") from exc
    return {"sharing": [path.name for path in paths],
            "note": "The Windows share sheet is open; the person picks where it goes."}


def send_to_phone(ctx: ToolContext, args: dict) -> dict:
    if not ctx.services.open_files_tab():  # the QR code and the indicator live in the island
        raise ToolError("The phone link shows its QR code in the Island, which is switched "
                        "off. Turn it on in Settings → General first.")
    paths = _files(ctx, args["file"]) if args.get("file") else []
    phone = ctx.services.phone
    if not phone.start(paths):
        raise ToolError(phone.error)
    return {"phone_link": "open", "offered": [path.name for path in paths],
            "minutes_left": round(phone.remaining_s() / 60),
            "note": "A QR code is showing in the island's Files & Share tab: scan it with the "
                    "phone's camera. Files sent from the phone need a click to accept."}


def stop_phone_link(ctx: ToolContext, args: dict) -> dict:
    phone = ctx.services.phone
    was_running = phone.running
    phone.stop()
    return {"stopped": was_running}


def _phone_summary(args: dict) -> str:
    file = (args.get("file") or "").strip()
    if not file:
        return "open the phone link (a QR code on your home Wi-Fi)"
    if file.lower() in ("this", "selected", "it"):
        return "let your phone download the selected file over your home Wi-Fi"
    return f"let your phone download “{file}” over your home Wi-Fi"


def tools() -> list[Tool]:
    return [
        Tool("share_file", "Open the Windows share sheet (Nearby Sharing, Mail and other apps) "
             "for a file. Use for 'share this', 'share the file I just downloaded'.",
             obj({"file": string(FILE_HELP)}), share_file, "files", runs_on="ui",
             summary=lambda a: f"share {a.get('file') or 'the selected file'}"),
        Tool("send_to_phone", "Open the phone link: a QR code the person scans to download a "
             "file to their phone or send files from the phone to the PC (same Wi-Fi). Use for "
             "'send this to my phone'. Without a file it only opens the link.",
             obj({"file": string(FILE_HELP + "; leave out to only receive")}), send_to_phone,
             "files", runs_on="ui", risk=Risk.CONFIRM, schedulable=False,
             summary=_phone_summary),
        Tool("stop_phone_link", "Close the phone link now.", obj({}), stop_phone_link, "files",
             runs_on="ui"),
    ]
