"""Which file a voice request means (D-051): "send this to my phone", "share the file I just
downloaded", "share the report on my shelf", or a name or path.

* "this" / "selected" / nothing: the files selected in the File Explorer window in front
  (Shell.Application → Windows() → each window's HWND and Document.SelectedItems(), FolderItem
  .Path). With several Explorer tabs open, a tab with a selection is used. Otherwise the newest
  file on the shelf.
* "latest download": the newest finished file in Downloads.
* "shelf": the newest file on the shelf.
* anything else: a path (expanded like other file tools), or the best match of a file search
  when it is a clear one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from wisp.winapi import files as fs

THIS = {"", "this", "that", "it", "selected", "selection", "the selected file", "this file"}
DOWNLOAD = {"latest download", "last download", "latest downloaded", "just downloaded",
            "the file i just downloaded", "download", "downloaded", "newest download"}
SHELF = {"shelf", "the shelf", "on the shelf", "shelved"}
CLEAR_MATCH = 88


class NotFound(Exception):
    """No file matches, with what to say to the person."""


def explorer_selection(foreground_hwnd: int) -> list[Path]:
    """Paths selected in the File Explorer window ``foreground_hwnd`` (none if it isn't one)."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    shell = win32com.client.Dispatch("Shell.Application")
    selected: list[Path] = []
    for window in shell.Windows():
        try:
            if int(window.HWND) != foreground_hwnd:
                continue
            items = window.Document.SelectedItems()
            paths = [Path(items.Item(index).Path) for index in range(items.Count)]
        except Exception:  # not a folder view (e.g. a web page) or the window went away
            continue
        if paths:
            selected = paths
            break
    return [path for path in selected if path.exists()]


def resolve(text: str | None, finder, shelf,
            selection: Callable[[], list[Path]] = lambda: []) -> list[Path]:
    """The file(s) meant by ``text``, or NotFound."""
    key = " ".join((text or "").lower().replace("’", "'").split())
    if key in THIS:
        picked = [path for path in selection() if path.is_file()]
        if picked:
            return picked
        newest = shelf.newest() if shelf is not None else None
        if newest is not None and newest.path.is_file():
            return [newest.path]
        raise NotFound("Select the file in File Explorer (or put it on the shelf) and ask "
                       "again, or say its name.")
    recent_words = ("just", "latest", "last", "newest")
    if key in DOWNLOAD or ("download" in key and any(word in key for word in recent_words)):
        latest = finder.latest_download()
        if latest is None:
            raise NotFound("There's nothing in your Downloads folder.")
        return [latest.path]
    if key in SHELF:
        newest = shelf.newest() if shelf is not None else None
        if newest is None:
            raise NotFound("The shelf is empty.")
        return [newest.path]
    path = fs.resolve_path(text or "")
    if path.is_file():
        return [path]
    results = finder.search(text or "", 3)
    if results and results[0].score >= CLEAR_MATCH and results[0].path.is_file():
        return [results[0].path]
    if results:
        raise NotFound("Which file? I found: " + ", ".join(r.name for r in results[:3]) + ".")
    raise NotFound(f"I couldn't find a file called “{text}”.")
