"""D-050: the Calendar tab, Settings → Accounts, the calendar voice tools (calendar_list,
calendar_create with its confirmation text) and the wallpaper tool and picker that replaced the
Wallpaper tab. A fake Google API (tests/test_gcal.py) is used throughout."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from tests.test_gcal import DESKTOP, FakeApi, MemorySecret
from wisp.db import Database
from wisp.gcal.store import CalendarStore
from wisp.tools.base import Origin, ToolContext, ToolError

pytestmark = pytest.mark.qt
NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


@pytest.fixture
def calendar(qtbot, tmp_path):
    from wisp.gcal.service import CalendarService

    api = FakeApi()
    service = CalendarService(CalendarStore(Database(tmp_path / "wisp.sqlite3")), MemorySecret(),
                              MemorySecret(), api_factory=api.bind,
                              authorize=lambda config, scopes: {"token": "t", "refresh_token": "r",
                                                                "scopes": scopes},
                              revoke=lambda info: True, now=lambda: NOW)
    service.api = api
    return service


def connect(service, qtbot, allow_create=False):
    service.import_client(DESKTOP)
    service.connect_account(allow_create)
    qtbot.waitUntil(lambda: service.busy is None and service.store.count() > 0, timeout=3000)


def ctx(service):
    return ToolContext(Origin.VOICE, SimpleNamespace(calendar=service))


# ----- tools ------------------------------------------------------------------------------------
def test_calendar_list_reads_the_cache_in_local_time(calendar, qtbot, monkeypatch):
    from wisp.tools.builtin import calendar as tools

    with pytest.raises(ToolError, match="isn't connected"):
        tools.calendar_list(ctx(calendar), {})
    connect(calendar, qtbot)
    result = tools.calendar_list(ctx(calendar), {"start": "2026-10-13", "days": 4})
    days = {d["date"]: d["events"] for d in result["days"]}
    assert days["2026-10-13"] == [{"title": "Standup", "time": "10:00–11:00"}]  # BST
    assert days["2026-10-14"] == [{"title": "Dentist", "time": "15:00–16:00"}]
    assert days["2026-10-15"][0] == {"title": "Half-term", "time": "All day"}
    assert result["time_zone"] == "Europe/London" and "last_synced" in result


def test_calendar_create_confirms_with_title_time_and_calendar(calendar, qtbot):
    from wisp.app import WispApp  # noqa: F401  (the registry is built the same way)
    from wisp.tools.base import Risk
    from wisp.tools.builtin import calendar as tools

    tool = next(t for t in tools.tools() if t.name == "calendar_create")
    assert tool.risk == Risk.CONFIRM and not tool.schedulable
    args = {"title": "Dentist", "start": "2026-10-14T15:00", "minutes": 30, "calendar": "Me"}
    assert tool.describe(args) == "add “Dentist” to Me, Wed 14 Oct 15:00–15:30"
    connect(calendar, qtbot)  # read-only
    with pytest.raises(ToolError, match="isn't allowed to add events"):
        tools.calendar_create(ctx(calendar), args)
    calendar.disconnect()
    qtbot.waitUntil(lambda: calendar.busy is None, timeout=3000)
    connect(calendar, qtbot, allow_create=True)
    result = tools.calendar_create(ctx(calendar), args)
    assert result["created"] == "Dentist" and result["calendar"] == "Me"
    _calendar_id, body = calendar.api.inserted[-1]
    assert body["start"] == {"dateTime": "2026-10-14T15:00:00+01:00", "timeZone": "Europe/London"}
    with pytest.raises(ToolError, match="don't own"):
        tools.calendar_create(ctx(calendar), {**args, "calendar": "UK holidays"})
    with pytest.raises(ToolError, match="end after it starts"):
        tools.calendar_create(ctx(calendar), {**args, "end": "2026-10-14T14:00"})


# ----- the tab -----------------------------------------------------------------------------------
@pytest.fixture
def tab(qtbot, calendar):
    from wisp.ui.island.calendar_tab import CalendarTab

    widget = CalendarTab(calendar, now=lambda: NOW.astimezone(calendar.tz()))
    qtbot.addWidget(widget)
    return widget


def labels(layout):
    out = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if widget is None:
            continue
        item = getattr(widget, "item", None)
        out.append(item.title if item is not None else widget.text())
    return out


def test_tab_asks_to_connect_then_shows_the_agenda(tab, calendar, qtbot):
    tab.show()
    tab.refresh()
    assert not tab.prompt.isHidden() and tab.prompt_button.text() == "Connect Google Calendar"
    with qtbot.waitSignal(tab.open_accounts):
        tab.prompt_button.click()
    connect(calendar, qtbot)
    tab.rebuild()
    assert tab.prompt.isHidden()
    assert labels(tab.agenda_layout)[:6] == ["Today", "Standup", "Tomorrow", "Dentist",
                                             "Thu 15 Oct", "Half-term"]
    assert tab.status.text() == "Synced just now"


def test_tab_offline_reconnect_and_month_view(tab, calendar, qtbot):
    tab.show()
    connect(calendar, qtbot)
    calendar.error = "Couldn't reach Google Calendar (ConnectionError)."
    tab.rebuild()
    assert tab.status.text().startswith("Offline · synced")
    assert "Dentist" in labels(tab.agenda_layout)
    calendar.needs_reconnect, calendar.error = True, "Google sign-in expired."
    tab.rebuild()
    assert tab.prompt_button.text() == "Reconnect" and not tab.prompt.isHidden()
    calendar.needs_reconnect, calendar.error = False, ""
    tab.views.button(1).click()
    assert tab.stack.currentIndex() == 1 and tab.month_title.text() == "October 2026"
    assert tab.grid.dots[date(2026, 10, 14)]  # the dentist's dot, in the calendar's colour
    tab.grid.selected = date(2026, 10, 14)
    tab._fill_day()
    assert "Dentist" in labels(tab.day_layout)
    tab._move_month(1)
    assert tab.month_title.text() == "November 2026"


def test_event_click_opens_google_calendar(tab, calendar, qtbot, monkeypatch):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from wisp.ui.island import calendar_tab

    opened = []
    monkeypatch.setattr(calendar_tab.QDesktopServices, "openUrl",
                        lambda url: opened.append(url.toString()))
    tab.show()
    connect(calendar, qtbot)
    tab.rebuild()
    row = next(tab.agenda_layout.itemAt(i).widget() for i in range(tab.agenda_layout.count())
               if isinstance(tab.agenda_layout.itemAt(i).widget(), calendar_tab.EventRow))
    point = QPointF(5, 5)
    row.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, point, point,
                                      Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                                      Qt.KeyboardModifier.NoModifier))
    assert opened and opened[0].startswith("https://www.google.com/calendar/event")


# ----- Settings → Accounts ---------------------------------------------------------------------
def test_accounts_page_imports_connects_and_shows_calendars(qtbot, calendar, tmp_path):
    from wisp.settings import Settings
    from wisp.ui.settings.accounts_page import AccountsPage

    page = AccountsPage(calendar)
    qtbot.addWidget(page)
    settings = Settings()
    page.load(settings)
    assert not page.connect_button.isEnabled() and page.client.text() == "not imported yet"
    bad = tmp_path / "web.json"
    bad.write_text('{"web": {"client_id": "x"}}', encoding="utf-8")
    page.import_file(str(bad))
    assert "Desktop app" in page.client_error.text()
    good = tmp_path / "client.json"
    good.write_text(DESKTOP, encoding="utf-8")
    page.import_file(str(good))
    assert page.client.text() == "123…apps.googleusercontent.com"
    assert page.connect_button.isEnabled()
    page.connect_button.click()
    qtbot.waitUntil(lambda: calendar.busy is None and calendar.store.count() > 0, timeout=3000)
    page.refresh()
    assert page.status.text().startswith("Connected · 3 calendars · read-only")
    boxes = [page.calendars_layout.itemAt(i).widget() for i in range(page.calendars_layout.count())]
    titles = [b.text() for b in boxes if hasattr(b, "isChecked")]
    assert titles == ["Me  (main)", "Family", "UK holidays"]
    page.allow_create.setChecked(True)
    assert not page.scope_note.isHidden() and page.connect_button.text() == "Reconnect"
    page.heads_up.setValue(15)
    page.apply(settings)
    assert (settings.calendar.allow_create, settings.calendar.heads_up_min) == (True, 15)
    page.disconnect_button.click()
    qtbot.waitUntil(lambda: calendar.busy is None, timeout=3000)
    assert page.status.text() == "Not connected."


# ----- wallpaper (voice tool and the Settings picker) ------------------------------------------
def test_wallpaper_tool_only_sets_listed_images(monkeypatch, tmp_path):
    from wisp.system import wallpaper
    from wisp.tools.builtin import system

    images = [tmp_path / "Mountain lake.jpg", tmp_path / "City at night.png"]
    for image in images:
        image.write_bytes(b"x")
    applied = []
    monkeypatch.setattr(wallpaper, "list_images", lambda: images)
    monkeypatch.setattr(wallpaper, "current", lambda: str(images[0]))
    monkeypatch.setattr(wallpaper, "set_wallpaper", applied.append)  # never the real desktop
    context = ToolContext(Origin.VOICE, SimpleNamespace())
    assert system.wallpaper_tool(context, {"action": "current"}) == {"current": "Mountain lake.jpg"}
    assert system.wallpaper_tool(context, {"action": "list"})["images"] == ["Mountain lake",
                                                                           "City at night"]
    assert system.wallpaper_tool(context, {"action": "set", "image": "city night"}) == {
        "wallpaper": "City at night.png"}
    assert applied == [str(images[1])]
    with pytest.raises(ToolError):
        system.wallpaper_tool(context, {"action": "set", "image": "C:/Windows/evil.bmp"})


def test_loadout_page_has_the_wallpaper_picker(qtbot, monkeypatch):
    from wisp.settings import Settings
    from wisp.system import wallpaper
    from wisp.ui.settings.loadout_page import LoadoutPage

    monkeypatch.setattr(wallpaper, "current", lambda: r"C:\Users\me\Pictures\Lake.jpg")
    opened = []
    page = LoadoutPage(open_wallpaper=opened.append)
    qtbot.addWidget(page)
    page.load(Settings())
    assert page.wallpaper.text() == "Lake.jpg"
    page._change_wallpaper()
    assert opened == [page]


def test_island_tabs_have_calendar_and_no_wallpaper(qtbot, isolated_data_dir, monkeypatch):
    import logging
    import sys
    import threading

    from PySide6.QtWidgets import QApplication

    from wisp.app import WispApp

    # WispApp sets up logging and the exception hooks for the whole process: put them back.
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    wisp = WispApp(QApplication.instance(), background=True)
    try:
        names = [name for name, _widget in wisp.island.panel.tabs]
        assert "Calendar" in names and "Wallpaper" not in names
        assert names.index("Calendar") == names.index("Today") + 1
        for tool in ("wallpaper", "calendar_list", "calendar_create"):
            assert wisp.registry.get(tool) is not None
        assert "Accounts" in [page.title for page in wisp.settings_pages()]
    finally:
        wisp.quit()
        for handler in root.handlers:
            if handler not in handlers:
                handler.close()
        root.handlers[:] = handlers
        root.setLevel(level)
