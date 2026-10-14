"""D-051: the Files & Share tab (search for apps and files, shelf, lists, actions, phone card),
files dropped on the island, the island's "Phone link" activity, the sharing voice tools, and
the WinRT pieces behind the share sheet (IIDs, a COM object written in Python)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_island import FakeIndex, RunningBackground
from tests.test_island_window import island  # noqa: F401  (the island fixture)
from wisp.db import Database
from wisp.files.finder import FileFinder
from wisp.files.shelf import Shelf
from wisp.tools.base import Origin, Risk, ToolContext, ToolError

pytestmark = pytest.mark.qt


class FakePhone:
    def __init__(self):
        from PySide6.QtCore import QObject, Signal

        class Signals(QObject):
            changed = Signal()

        self._signals = Signals()
        self.changed = self._signals.changed
        self.running = False
        self.error = ""
        self.url = ""
        self.network = "Home"
        self.waiting = []
        self.started = []
        self.decisions = []
        self.ends_at = 0.0

    def start(self, paths=None):
        self.started.append(list(paths or []))
        self.running, self.url = True, "http://192.168.1.20:5000/" + "t" * 43 + "/"
        self.changed.emit()
        return True

    def stop(self):
        self.running = False
        self.changed.emit()

    def offers(self):
        return [p for batch in self.started for p in batch]

    def remaining_s(self):
        return 541.0

    def accept(self, upload):
        self.decisions.append((upload.name, True))

    def decline(self, upload):
        self.decisions.append((upload.name, False))


@pytest.fixture
def files(tmp_path, monkeypatch):
    from wisp.ui.island import files_tab

    monkeypatch.setattr(files_tab, "icon_png", lambda *_args, **_kw: None)  # glyph fallback
    docs = tmp_path / "Documents"
    downloads = tmp_path / "Downloads"
    docs.mkdir()
    downloads.mkdir()
    report = docs / "Quarterly report.docx"
    report.write_text("x")
    invoice = downloads / "invoice-0912.pdf"
    invoice.write_text("x")
    finder = FileFinder([docs], index=lambda _sql: [(report, time.time())],
                        downloads_folder=downloads)
    monkeypatch.setattr(FileFinder, "recent", staticmethod(lambda limit=12: []))
    return SimpleNamespace(finder=finder, shelf=Shelf(Database(":memory:")), report=report,
                           invoice=invoice, tmp=tmp_path)


@pytest.fixture
def tab(qtbot, files):
    from wisp.ui import theme
    from wisp.ui.island.files_tab import FilesTab

    shared = []
    widget = FilesTab(files.finder, files.shelf, FakeIndex(), FakePhone(), RunningBackground(),
                      theme.palette("dark", "#7c5cff"), share=shared.append,
                      confirm=lambda _q: True)
    widget.shared = shared
    qtbot.addWidget(widget)
    widget.refresh()
    return widget


def texts(widget):
    return [widget.item(i).text() for i in range(widget.count())]


def test_one_search_box_finds_apps_and_files(tab, qtbot, files):
    tab.search.setText("calc")
    tab._run_search()
    assert tab.stack.currentIndex() == 1
    assert texts(tab.results)[:2] == ["Apps", "Calculator"]
    tab.search.returnPressed.emit()
    assert tab.apps.launched == ["Calculator"]
    tab.search.setText("quarterly")
    tab._run_search()
    found = texts(tab.results)
    assert "Files" in found and any(t.startswith("Quarterly report.docx") for t in found)
    tab.search.clear()
    assert tab.stack.currentIndex() == 0


def test_shelf_strip_and_lists(tab, files):
    assert "Drop files" in tab.shelf_hint.text()
    tab.shelf_list.dropped.emit([files.report])
    assert texts(tab.shelf_list) == ["Quarterly report.docx"]
    assert "Parked 1 item" in tab.status.text()
    tab.lists.button(1).click()
    assert texts(tab.places)[0].startswith("invoice-0912.pdf")
    mime = tab.places.mimeData([tab.places.item(0)])  # dragging out carries the file
    assert [Path(url.toLocalFile()) for url in mime.urls()] == [files.invoice]
    tab.lists.button(0).click()
    assert texts(tab.places) == ["Nothing here yet."]


def test_quick_actions_confirm_before_the_recycle_bin(tab, files, monkeypatch):
    from wisp.files import actions

    recycled = []
    monkeypatch.setattr(actions, "recycle", lambda path: recycled.append(path))
    tab.confirm = lambda question: "Recycle Bin" in question and False
    tab._recycle([files.report])
    assert recycled == []  # said no
    tab.confirm = lambda question: True
    tab._recycle([files.report])
    assert recycled == [files.report] and "Recycle Bin" in tab.status.text()
    tab._share([files.report])
    assert tab.shared == [[files.report]]
    monkeypatch.setattr("wisp.ui.island.files_tab.QInputDialog.getText",
                        lambda *_a, **_k: ("Q3 report.docx", True))
    tab._rename(files.report)
    assert (files.report.parent / "Q3 report.docx").exists()
    assert "Renamed" in tab.status.text()


def test_phone_card_shows_the_qr_and_asks_about_each_file(tab, qtbot):
    from wisp.phone.server import Upload

    phone = tab.phone
    assert tab.phone_card.isHidden()
    tab.phone_button.click()
    assert not tab.phone_card.isHidden() and tab.phone_button.isChecked()
    assert tab.qr_label.pixmap().width() > 0 and "Home" in tab.phone_text.text()
    assert tab.phone_time.text() == "Stops in 9:01"
    phone.waiting.append(Upload(7, "holiday.jpg", 2_400_000, "192.168.1.30"))
    phone.changed.emit()
    buttons = [tab.waiting_box.itemAt(0).layout().itemAt(i).widget() for i in (1, 2)]
    assert [b.text() for b in buttons] == ["Accept", "Decline"]
    phone.changed.emit()  # an unchanged list keeps its buttons
    assert tab.waiting_box.itemAt(0).layout().itemAt(1).widget() is buttons[0]
    buttons[0].click()
    assert phone.decisions == [("holiday.jpg", True)]
    phone.error, phone.running = "“Cafe” is set up as a Public network", False
    phone.changed.emit()
    assert tab.phone_text.text().startswith("“Cafe”") and not tab.phone_retry.isHidden()
    assert tab.qr_label.isHidden()


def test_files_dropped_on_the_island_open_the_shelf(island, files):  # noqa: F811
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    opened = []
    island.open_tab = opened.append
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(files.report))])
    point = QPointF(10, 10)
    enter = QDragEnterEvent(point, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
    island.dragEnterEvent(enter)
    assert enter.isAccepted() and opened == ["Files & Share"] and island._hover
    dropped = []
    island.files_dropped.connect(dropped.append)
    drop = QDropEvent(point, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)
    island.dropEvent(drop)
    assert drop.isAccepted() and dropped == [[files.report]]
    text = QMimeData()
    text.setText("just text")
    ignored = QDragEnterEvent(point, Qt.DropAction.CopyAction, text, Qt.MouseButton.LeftButton,
                              Qt.KeyboardModifier.NoModifier)
    island.dragEnterEvent(ignored)
    assert not ignored.isAccepted()


def test_phone_link_keeps_the_island_up_with_its_time_left():
    from wisp.ui.island.machine import IslandStateMachine

    clock = [0.0]
    machine = IslandStateMachine(clock=lambda: clock[0])
    machine.set_autohide(True, 3000)
    machine.set_sharing("Phone link", 1600.0)
    clock[0] = 60.0
    machine.update()
    assert not machine.hideable()
    assert machine.presentation.mode == "activity"
    assert machine.presentation.main.kind == "sharing" and machine.presentation.main.data == 1600.0
    machine.set_sharing(None)
    clock[0] = 120.0
    machine.update()
    assert machine.presentation.mode == "away"


# ----- voice tools -------------------------------------------------------------------------------
def tool(name):
    from wisp.tools.builtin import share

    return next(t for t in share.tools() if t.name == name)


def test_send_to_phone_is_confirmed_and_names_the_file(files, monkeypatch):
    from wisp.tools.builtin import share

    send = tool("send_to_phone")
    assert send.risk == Risk.CONFIRM and send.runs_on == "ui" and not send.schedulable
    assert send.describe({"file": "this"}) == ("let your phone download the selected file over "
                                               "your home Wi-Fi")
    assert "phone link" in send.describe({})
    phone = FakePhone()
    opened = []
    services = SimpleNamespace(finder=files.finder, shelf=files.shelf, phone=phone,
                               open_files_tab=lambda: opened.append(True) or True)
    monkeypatch.setattr(share, "explorer_selection", lambda _hwnd: [files.report])
    result = share.send_to_phone(ToolContext(Origin.VOICE, services), {"file": "this"})
    assert result["offered"] == ["Quarterly report.docx"] and phone.started == [[files.report]]
    assert opened == [True] and result["minutes_left"] == 9
    phone.start = lambda paths=None: False
    phone.error = "“Cafe” is set up as a Public network"
    with pytest.raises(ToolError, match="Public"):
        share.send_to_phone(ToolContext(Origin.VOICE, services), {})
    services.open_files_tab = lambda: False  # the island is switched off
    with pytest.raises(ToolError, match="Island"):
        share.send_to_phone(ToolContext(Origin.VOICE, services), {})


def test_share_the_file_i_just_downloaded(files, monkeypatch):
    from wisp.tools.builtin import share

    shared = []
    services = SimpleNamespace(finder=files.finder, shelf=files.shelf, share_files=shared.append)
    result = share.share_file(ToolContext(Origin.VOICE, services),
                              {"file": "the file I just downloaded"})
    assert shared == [[files.invoice]] and result["sharing"] == ["invoice-0912.pdf"]
    monkeypatch.setattr(share, "explorer_selection", lambda _hwnd: [])
    with pytest.raises(ToolError, match="Select the file"):
        share.share_file(ToolContext(Origin.VOICE, services), {"file": "this"})
    assert tool("share_file").risk == Risk.SAFE and tool("share_file").runs_on == "ui"


# ----- the share sheet's WinRT plumbing ---------------------------------------------------------
@pytest.mark.windows
def test_parameterized_iids_follow_the_winrt_algorithm():
    from wisp.winapi import share
    from wisp.winapi import winrt_abi as abi

    iterable_of_string = abi.pinterface_iid(share.ITERABLE, "string")
    assert iterable_of_string == uuid.UUID("e2fcc7c1-3bfc-5a0b-b2b0-72e769d1cb7e")
    assert abi.GUID.of(share.IID_ITEM).uuid() == share.IID_ITEM
    assert share.IID_ITEMS != share.IID_ITEM_ITERATOR != share.IID_HANDLER


@pytest.mark.windows
def test_a_python_com_object_answers_query_interface_and_counts_references():
    from ctypes import HRESULT, WINFUNCTYPE, c_int32, c_void_p

    from wisp.winapi import winrt_abi as abi

    custom = uuid.UUID("11111111-2222-3333-4444-555555555555")
    calls = []

    def invoke(value) -> int:
        calls.append(value)
        return abi.S_OK

    obj = abi.ComObject([custom], [(WINFUNCTYPE(HRESULT, c_void_p, c_int32), invoke)])
    pointer = obj.new_reference()
    same = abi.query(pointer, custom)
    assert same.value == pointer.value
    assert abi.query(pointer, abi.IID_IAGILEOBJECT).value == pointer.value
    with pytest.raises(OSError):
        abi.query(pointer, uuid.UUID("99999999-2222-3333-4444-555555555555"))
    abi.call(pointer, 3, [c_int32], 42)
    assert calls == [42] and obj._refs == 3
    for _ in range(3):
        abi.release(pointer)
    assert obj._refs == 0 and id(obj) not in abi.ComObject._alive
    failing = abi.ComObject([custom], [(WINFUNCTYPE(HRESULT, c_void_p), lambda: 1 / 0)])
    with pytest.raises(OSError):
        abi.call(failing.new_reference(), 3)  # an exception in Python becomes E_FAIL


@pytest.mark.windows
def test_storage_items_for_a_real_file(tmp_path):
    from wisp.winapi import share
    from wisp.winapi import winrt_abi as abi

    sample = tmp_path / "share me.txt"
    sample.write_text("x")
    items = share.storage_items([sample])
    try:
        assert len(items) == 1 and items[0].value
    finally:
        for item in items:
            abi.release(item)
    with pytest.raises(OSError):
        share.storage_items([tmp_path / "missing.txt"])
