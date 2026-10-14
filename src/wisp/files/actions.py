"""File quick actions (D-051): open, show in Explorer, copy, copy path, rename, move and move to
the Recycle Bin. Nothing here deletes permanently: the only delete is the Recycle Bin
(SHFileOperation with FOF_ALLOWUNDO, wisp.winapi.files.recycle), and it refuses Windows, program
and top-level personal folders. Renaming and moving never overwrite an existing file.

Copying puts the files on the clipboard as file URLs; Qt turns text/uri-list into CF_HDROP, so
Explorer's Paste works.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from pathlib import Path

from wisp.files import names
from wisp.winapi import files as fs


class ActionError(Exception):
    """A file action that can't be done, with a message for the person."""


def open_file(path: Path) -> None:
    if not path.exists():
        raise ActionError(f"{path.name} isn't there any more.")
    fs.open_path(path)


def reveal(path: Path) -> None:
    if not path.exists():
        raise ActionError(f"{path.name} isn't there any more.")
    fs.reveal(path)


def copy_files(paths: Iterable[Path], clipboard=None) -> int:
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtGui import QGuiApplication

    urls = [QUrl.fromLocalFile(str(path)) for path in paths if path.exists()]
    if not urls:
        raise ActionError("Nothing to copy: the file isn't there any more.")
    mime = QMimeData()
    mime.setUrls(urls)
    (clipboard or QGuiApplication.clipboard()).setMimeData(mime)
    return len(urls)


def copy_path(paths: Iterable[Path], clipboard=None) -> str:
    from PySide6.QtGui import QGuiApplication

    text = "\n".join(str(path) for path in paths)
    (clipboard or QGuiApplication.clipboard()).setText(text)
    return text


def rename(path: Path, new_name: str, on_moved: Callable[[Path, Path], None] | None = None
           ) -> Path:
    new_name = new_name.strip()
    problem = names.valid_new_name(new_name)
    if problem:
        raise ActionError(problem)
    if not path.exists():
        raise ActionError(f"{path.name} isn't there any more.")
    target = path.with_name(new_name)
    if target == path:
        return path
    if target.exists() and target.name.lower() != path.name.lower():
        raise ActionError(f"There's already something called {new_name} there.")
    try:
        path.rename(target)
    except OSError as exc:
        raise ActionError(f"Windows couldn't rename it ({exc.strerror or exc}).") from exc
    if on_moved:
        on_moved(path, target)
    return target


def move(path: Path, folder: Path, on_moved: Callable[[Path, Path], None] | None = None) -> Path:
    if not path.exists():
        raise ActionError(f"{path.name} isn't there any more.")
    if not folder.is_dir():
        raise ActionError(f"{folder} isn't a folder.")
    target = folder / path.name
    if target.exists():
        raise ActionError(f"{folder.name} already has something called {path.name}.")
    if path.is_dir() and (folder.resolve() == path.resolve()
                          or path.resolve() in folder.resolve().parents):
        raise ActionError("A folder can't be moved into itself.")
    try:
        moved = Path(shutil.move(str(path), str(target)))
    except OSError as exc:
        raise ActionError(f"Windows couldn't move it ({exc.strerror or exc}).") from exc
    if on_moved:
        on_moved(path, moved)
    return moved


def recycle(path: Path, recycler: Callable[[Path], None] = fs.recycle) -> None:
    """Move to the Recycle Bin (never a permanent delete). Callers confirm first."""
    reason = fs.protected_reason(path)
    if reason:
        raise ActionError(reason)
    try:
        recycler(path)
    except OSError as exc:
        raise ActionError(str(exc)) from exc
