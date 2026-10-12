"""Raw clipboard access: exact snapshot/restore, excluded writes, exclusion checks.

Sources:
* learn.microsoft.com/windows/win32/dataxchg/clipboard-formats — the registered formats
  ExcludeClipboardContentFromMonitorProcessing, CanIncludeInClipboardHistory and
  CanUploadToCloudClipboard keep data out of clipboard history/sync (password managers use them).
* EmptyClipboard: opening with a NULL window makes SetClipboardData fail, and the owner window
  receives WM_DESTROYCLIPBOARD synchronously — so writes use a window owned by the Qt thread,
  which pumps messages. Call these functions on the Qt UI thread.
* pywin32: GetClipboardDataHandle + GetGlobalMemory copy a format's bytes; SetClipboardData copies
  a buffer into new global memory.
"""

from __future__ import annotations

import logging
import struct
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import win32clipboard as wcb

log = logging.getLogger(__name__)

# GDI handles and synthesized formats cannot (or need not) be copied as bytes.
SKIP_FORMATS = {
    wcb.CF_BITMAP, wcb.CF_PALETTE, wcb.CF_ENHMETAFILE, wcb.CF_METAFILEPICT, wcb.CF_DSPBITMAP,
    wcb.CF_DSPENHMETAFILE, wcb.CF_DSPMETAFILEPICT, wcb.CF_OWNERDISPLAY, wcb.CF_TEXT,
    wcb.CF_OEMTEXT, wcb.CF_LOCALE,
}
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


def _formats() -> dict[str, int]:
    return {
        "exclude": wcb.RegisterClipboardFormat("ExcludeClipboardContentFromMonitorProcessing"),
        "history": wcb.RegisterClipboardFormat("CanIncludeInClipboardHistory"),
        "cloud": wcb.RegisterClipboardFormat("CanUploadToCloudClipboard"),
        "png": wcb.RegisterClipboardFormat("PNG"),
        "html": wcb.RegisterClipboardFormat("HTML Format"),
    }


FORMATS = _formats()


@dataclass
class Snapshot:
    items: list[tuple[int, bytes]] = field(default_factory=list)
    sequence: int = 0

    @property
    def empty(self) -> bool:
        return not self.items


class ClipboardBusy(RuntimeError):
    pass


@contextmanager
def opened(owner_hwnd: int | None, attempts: int = 20) -> Iterator[None]:
    for _ in range(attempts):
        try:
            wcb.OpenClipboard(owner_hwnd)
            break
        except wcb.error:
            time.sleep(0.025)  # another app holds the clipboard briefly
    else:
        raise ClipboardBusy("The clipboard is busy; try again.")
    try:
        yield
    finally:
        wcb.CloseClipboard()


def sequence() -> int:
    return wcb.GetClipboardSequenceNumber()


def _read_raw(fmt: int) -> bytes | None:
    try:
        handle = wcb.GetClipboardDataHandle(fmt)
        if not handle:
            return None
        return bytes(wcb.GetGlobalMemory(handle))
    except wcb.error:
        return None


def snapshot(owner_hwnd: int | None = None) -> Snapshot:
    snap = Snapshot(sequence=sequence())
    total = 0
    with opened(owner_hwnd):
        fmt = wcb.EnumClipboardFormats(0)
        while fmt:
            if fmt not in SKIP_FORMATS:
                data = _read_raw(fmt)
                if data is not None and total + len(data) <= MAX_SNAPSHOT_BYTES:
                    snap.items.append((fmt, data))
                    total += len(data)
            fmt = wcb.EnumClipboardFormats(fmt)
    return snap


def _mark_excluded() -> None:
    zero = struct.pack("<I", 0)
    wcb.SetClipboardData(FORMATS["exclude"], b"\x00")
    wcb.SetClipboardData(FORMATS["history"], zero)
    wcb.SetClipboardData(FORMATS["cloud"], zero)


def restore(snap: Snapshot, owner_hwnd: int, exclude_from_history: bool = True) -> None:
    """Put a snapshot back. Marked as excluded so history does not get a duplicate entry."""
    with opened(owner_hwnd):
        wcb.EmptyClipboard()
        for fmt, data in snap.items:
            if fmt in (FORMATS["exclude"], FORMATS["history"], FORMATS["cloud"]):
                continue
            try:
                wcb.SetClipboardData(fmt, data)
            except wcb.error as exc:
                log.debug("Format %s not restored: %s", fmt, exc)
        if exclude_from_history:
            _mark_excluded()


def set_text(text: str, owner_hwnd: int, exclude_from_history: bool = True) -> None:
    with opened(owner_hwnd):
        wcb.EmptyClipboard()
        wcb.SetClipboardData(wcb.CF_UNICODETEXT, text)
        if exclude_from_history:
            _mark_excluded()


def get_text(owner_hwnd: int | None = None) -> str | None:
    with opened(owner_hwnd):
        if wcb.IsClipboardFormatAvailable(wcb.CF_UNICODETEXT):
            return wcb.GetClipboardData(wcb.CF_UNICODETEXT)
    return None


def exclusion_requested() -> bool:
    """True if the current content asks monitors/history to skip it (password managers)."""
    if wcb.IsClipboardFormatAvailable(FORMATS["exclude"]):
        return True
    if wcb.IsClipboardFormatAvailable(FORMATS["history"]):
        data = _read_raw(FORMATS["history"])
        if data is not None and len(data) >= 4 and struct.unpack("<I", data[:4])[0] == 0:
            return True
    return False


@dataclass
class ClipContent:
    excluded: bool
    text: str | None = None
    png: bytes | None = None
    dib: bytes | None = None


def read_for_history(owner_hwnd: int | None = None) -> ClipContent:
    """Read what clipboard history needs, checking exclusion first."""
    with opened(owner_hwnd):
        if exclusion_requested():
            return ClipContent(excluded=True)
        content = ClipContent(excluded=False)
        if wcb.IsClipboardFormatAvailable(wcb.CF_UNICODETEXT):
            content.text = wcb.GetClipboardData(wcb.CF_UNICODETEXT)
        if wcb.IsClipboardFormatAvailable(FORMATS["png"]):
            content.png = _read_raw(FORMATS["png"])
        elif wcb.IsClipboardFormatAvailable(wcb.CF_DIB):
            content.dib = _read_raw(wcb.CF_DIB)
        return content
