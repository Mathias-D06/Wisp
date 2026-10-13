"""Clipboard history store (F7.10) and the monitor's exclusion handling (F7.11)."""

from __future__ import annotations

import pytest

from wisp.stores.clipboard_history import MAX_TEXT, ClipboardHistory
from wisp.system import clipboard
from wisp.system.clipboard import ClipContent


@pytest.fixture
def history(db):
    limit = {"n": 5}
    store = ClipboardHistory(db, lambda: limit["n"])
    store.limit = limit
    return store


def test_add_and_dedupe_moves_to_top(history):
    assert history.add_text("first")
    assert history.add_text("second")
    assert history.add_text("first")  # copied again → one row, newest
    assert [i.text for i in history.items()] == ["first", "second"]


def test_rejects_empty_whitespace_and_oversized(history):
    assert not history.add_text("")
    assert not history.add_text("   \n\t")
    assert not history.add_text("x" * (MAX_TEXT + 1))
    assert not history.add_image(b"")
    assert history.items() == []


def test_prunes_to_configured_size(history):
    for n in range(8):
        history.add_text(f"item {n}")
    assert [i.text for i in history.items()] == [f"item {n}" for n in (7, 6, 5, 4, 3)]
    history.limit["n"] = 2
    history.add_text("newest")
    assert [i.text for i in history.items()] == ["newest", "item 7"]


def test_search_text_only_and_literal(history):
    history.add_text("Invoice 2026_10 total 100%")
    history.add_text("Invoice 2026-10 draft")
    history.add_image(b"\x89PNG fake image bytes")
    assert len(history.items()) == 3
    assert [i.text for i in history.items("invoice")] == ["Invoice 2026-10 draft",
                                                         "Invoice 2026_10 total 100%"]
    assert [i.text for i in history.items("2026_10")] == ["Invoice 2026_10 total 100%"]
    assert [i.text for i in history.items("100%")] == ["Invoice 2026_10 total 100%"]
    assert history.items("%") == history.items("100%")


def test_images_dedupe_and_preview(history):
    history.add_image(b"png-a")
    history.add_image(b"png-b")
    history.add_image(b"png-a")
    items = history.items()
    assert [i.image for i in items] == [b"png-a", b"png-b"]
    assert items[0].preview == "Image"


def test_preview_collapses_whitespace(history):
    history.add_text("  line one\n\n   line\ttwo  ")
    assert history.items()[0].preview == "line one line two"


def test_delete_clear_and_listeners(history):
    calls = []
    history.subscribe(lambda: calls.append(1))
    history.add_text("a")
    history.add_text("b")
    item = history.items()[0]
    history.delete(item.id)
    assert [i.text for i in history.items()] == ["a"]
    assert history.get(item.id) is None
    history.clear()
    assert history.items() == []
    assert len(calls) == 4


# ----- ClipboardMonitor (Qt thread, clipboard reads faked) ---------------------------------------
@pytest.fixture
def monitor(qtbot, history, monkeypatch):
    from wisp.system.clipboard_monitor import ClipboardMonitor

    contents: list = []

    def fake_read(owner_hwnd=None):
        result = contents.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(clipboard, "read_for_history", fake_read)
    mon = ClipboardMonitor(history, owner_hwnd=0)
    mon.contents = contents
    return mon


@pytest.mark.qt
def test_monitor_skips_password_manager_content(monitor, history):
    monitor.contents.append(ClipContent(excluded=True, text="hunter2"))
    monitor.capture()
    assert monitor.skipped_excluded == 1
    assert history.items() == []


@pytest.mark.qt
def test_monitor_stores_text_and_png(monitor, history):
    monitor.contents += [ClipContent(excluded=False, text="hello"),
                         ClipContent(excluded=False, text="ignored alt text", png=b"png-data")]
    monitor.capture()
    monitor.capture()
    items = history.items()
    assert [(i.kind, i.text, i.image) for i in items] == [("image", None, b"png-data"),
                                                          ("text", "hello", None)]


@pytest.mark.qt
def test_monitor_retries_when_clipboard_busy(monitor, history, qtbot):
    monitor.contents += [clipboard.ClipboardBusy("locked"), ClipContent(excluded=False, text="x")]
    monitor.capture()
    assert history.items() == []
    qtbot.waitUntil(lambda: len(history.items()) == 1, timeout=2000)
