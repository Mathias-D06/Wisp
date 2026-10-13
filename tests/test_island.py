"""Island window (F7.1), music strip (F7.9), Today tab (F5.2/F5.4/F7.3) and Power tab (F7.8)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QEnterEvent, QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from wisp.system.media import MediaState
from wisp.ui import theme

pytestmark = pytest.mark.qt

FAR_AWAY = QPoint(-30000, -30000)


class FakeVoice(QObject):
    visual = Signal(str, float, str)

    def __init__(self):
        super().__init__()
        self.toggles = 0

    def toggle_talk(self):
        self.toggles += 1


class CountingTab(QWidget):
    def __init__(self):
        super().__init__()
        self.refreshes = 0

    def refresh(self):
        self.refreshes += 1


@pytest.fixture
def palette():
    return theme.palette("dark", "#7c5cff")


@pytest.fixture
def island(qtbot, palette, monkeypatch):
    from wisp.ui.island import island as island_mod

    cursor = SimpleNamespace(at=FAR_AWAY)
    monkeypatch.setattr(island_mod, "QCursor", SimpleNamespace(pos=lambda: cursor.at))
    key = {"has": False}
    commands = []
    tabs = [("Controls", CountingTab()), ("Today", CountingTab())]
    widget = island_mod.Island(FakeVoice(), palette, "#7c5cff", lambda: key["has"],
                               commands.append, tabs)
    qtbot.addWidget(widget)
    widget.key, widget.commands, widget.cursor = key, commands, cursor
    return widget


def test_pill_is_frameless_on_top_and_centred(island):
    from wisp.ui.island.island import COLLAPSED, MARGIN

    flags = island.windowFlags()
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.Tool
    assert island.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert not island.expanded and island.body.isHidden()
    assert island.size().width() == COLLAPSED[0] + 2 * MARGIN
    screen = QGuiApplication.primaryScreen().availableGeometry()
    assert abs(island.geometry().center().x() - screen.center().x()) <= 1
    assert island.y() <= screen.y() + 2


def test_hover_expands_and_leaving_collapses(island, qtbot):
    from wisp.ui.island.island import EXPANDED, MARGIN

    island.show()
    QApplication.sendEvent(island, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    qtbot.waitUntil(lambda: island.expanded, timeout=2000)
    assert not island.body.isHidden()
    assert island.size().width() == EXPANDED[0] + 2 * MARGIN
    screen = QGuiApplication.primaryScreen().availableGeometry()
    assert abs(island.geometry().center().x() - screen.center().x()) <= 1  # re-centred
    island.cursor.at = island.geometry().center()
    island._maybe_collapse()
    assert island.expanded  # pointer still over the island
    island.cursor.at = FAR_AWAY
    island._maybe_collapse()
    assert not island.expanded


def test_scroll_expands(island, qtbot):
    from PySide6.QtGui import QWheelEvent

    island.show()
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(island, event)
    assert island.expanded


def test_tabs_refresh_when_shown(island):
    controls, today = (widget for _name, widget in island.tabs)
    island.expand()
    assert controls.refreshes == 1
    island.open_tab("Today")
    assert island.stack.currentWidget() is today and today.refreshes == 1
    assert island.tab_group.checkedId() == 1
    island.tab_group.button(0).click()
    assert controls.refreshes == 2


def test_status_without_key_and_with_music(island):
    island.update_key_prompt()
    assert not island.key_prompt.isHidden()
    assert island.status.toolTip() == "Island ready · voice needs a key"
    island.show_media(MediaState(True, "Blue in Green", "Miles Davis", "Spotify", True, 30, 337))
    assert island.status.toolTip() == "♪ Blue in Green — Miles Davis"
    island.key["has"] = True
    island.show_media(MediaState())
    island.update_key_prompt()
    assert island.key_prompt.isHidden()
    island.voice.visual.emit("listening", 0.3, "Listening…")
    assert island.status.toolTip() == "Listening…"


def test_orb_click_and_settings_signal(island, qtbot):
    island.orb.clicked.emit()
    assert island.voice.toggles == 1
    with qtbot.waitSignal(island.settings_requested) as blocker:
        island.key_prompt.click()
    assert blocker.args == ["General"]


def test_music_strip(island):
    strip = island.music
    assert not strip.play.isEnabled() and strip.title.text() == "Nothing playing"
    strip.show_state(MediaState(True, "Song", "", "app", True, 61, 200))
    assert strip.play.isEnabled() and strip.time.text() == "1:01 / 3:20"
    assert strip.progress.value() == 305 and strip.artist.isHidden()
    strip.next.click()
    strip.play.click()
    assert island.commands == ["next", "play_pause"]


# ----- Today tab ---------------------------------------------------------------------------------
class FakeScheduler:
    def __init__(self, tasks):
        self.store = SimpleNamespace(subscribe=lambda listener: None)
        self.tasks = tasks

    def upcoming(self, limit):
        return self.tasks[:limit]


@pytest.fixture
def today(qtbot, db):
    from wisp.stores.todos import TodoStore
    from wisp.ui.island.today_tab import TodayTab

    store = TodoStore(db)
    when = datetime(2026, 10, 14, 9, 0)
    tab = TodayTab(store, FakeScheduler([(SimpleNamespace(title="Morning apps"), when)]))
    qtbot.addWidget(tab)
    return tab


def test_today_add_complete_delete(today, monkeypatch, qtbot):
    today.entry.setText("Water the plants")
    today.entry.returnPressed.emit()
    today.entry.setText("Call the bank")
    today._add()
    today.refresh()
    texts = [today.list.item(i).text() for i in range(today.list.count())]
    assert sorted(texts) == ["Call the bank", "Water the plants"]
    assert today.upcoming.item(0).text() == "Wed 09:00  Morning apps"
    first = today.list.item(0)
    first.setCheckState(Qt.CheckState.Checked)
    remaining = [t.text for t in today.todos.list()]
    assert first.text() not in remaining and len(remaining) == 1
    today.refresh()
    today.list.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    today._delete()
    assert today.todos.list() == []
    today.refresh()
    assert today.list.item(0).text().startswith("Nothing to do")


def test_today_due_time_is_shown(today):
    now = datetime.now().astimezone()
    today.todos.add("Stand-up", (now + timedelta(minutes=30)).replace(second=0, microsecond=0))
    today.refresh()
    assert "today" in today.list.item(0).text() or "tomorrow" in today.list.item(0).text()


# ----- Power tab ---------------------------------------------------------------------------------
class RecordingBackground:
    def __init__(self):
        self.calls = []

    def run(self, fn, on_done=None, on_error=None):
        self.calls.append(fn)  # never executed: these would really lock/restart the PC


def test_power_tab_asks_before_restart_and_logs(qtbot, db, palette):
    from wisp.stores.action_log import ActionLog
    from wisp.system import power
    from wisp.ui.island.power_tab import PowerTab

    answers, questions = [False, True], []

    def confirm(question):
        questions.append(question)
        return answers.pop(0)

    bg, log = RecordingBackground(), ActionLog(db)
    tab = PowerTab(bg, palette, log, confirm=confirm)
    qtbot.addWidget(tab)
    tab.buttons["restart"].click()
    assert bg.calls == [] and log.recent() == []
    tab.buttons["restart"].click()
    assert bg.calls == [power.restart]
    assert all("Restart" in q for q in questions)
    entry = log.recent()[0]
    assert entry.tool == "power" and "confirmed" in entry.decision


def test_power_tab_lock_needs_no_question(qtbot, palette):
    from wisp.system import power
    from wisp.ui.island.power_tab import PowerTab

    bg = RecordingBackground()
    tab = PowerTab(bg, palette, confirm=lambda q: pytest.fail("lock must not ask"))
    qtbot.addWidget(tab)
    tab.buttons["lock"].click()
    assert bg.calls == [power.lock]


# ----- Apps and Wallpaper tabs -------------------------------------------------------------------
class FakeIndex:
    def __init__(self):
        from wisp.system.app_index import AppEntry

        self.entries = [AppEntry(1, "Spotify", "Spotify.exe", "path", 3, False),
                        AppEntry(2, "Notepad", "notepad.exe", "path", 0, False),
                        AppEntry(3, "Calculator", "Microsoft.WindowsCalculator!App", "aumid", 0,
                                 False)]
        self.launched = []

    def all(self):
        return list(self.entries)

    def launch(self, entry):
        self.launched.append(entry.name)


class RunningBackground:
    """Runs work on the calling thread."""

    def run(self, fn, on_done=None, on_error=None):
        try:
            result = fn()
        except Exception as exc:
            if on_error:
                on_error(exc)
            return
        if on_done:
            on_done(result)


def test_apps_tab_search_and_launch(qtbot, palette, monkeypatch):
    from wisp.ui.island import apps_tab
    from wisp.ui.island.apps_tab import AppsTab

    monkeypatch.setattr(apps_tab, "icon_png", lambda name, size: None)  # fallback glyph
    index = FakeIndex()
    tab = AppsTab(index, RunningBackground(), palette)
    qtbot.addWidget(tab)
    tab.refresh()
    assert tab.grid.count() == 3
    tab.search.setText("calc")
    assert [tab.grid.item(i).text() for i in range(tab.grid.count())] == ["Calculator"]
    tab.search.returnPressed.emit()
    assert index.launched == ["Calculator"]
    tab.search.setText("zzzqqq")
    assert tab.grid.count() == 0 and "No apps found" in tab.status.text()


def test_wallpaper_rejects_non_images(tmp_path):
    from wisp.system import wallpaper

    text = tmp_path / "notes.txt"
    text.write_text("hi")
    with pytest.raises(ValueError):
        wallpaper.set_wallpaper(str(text))
    with pytest.raises(ValueError):
        wallpaper.set_wallpaper(str(tmp_path / "missing.png"))


def test_wallpaper_lists_images_recursively(tmp_path):
    from wisp.system import wallpaper

    (tmp_path / "sub").mkdir()
    (tmp_path / ".hidden").mkdir()
    for name in ("a.JPG", "sub/b.png", "sub/c.txt", ".hidden/d.png"):
        (tmp_path / name).write_bytes(b"x")
    found = sorted(p.name for p in wallpaper.list_images([tmp_path]))
    assert found == ["a.JPG", "b.png"]
    assert len(wallpaper.list_images([tmp_path], limit=1)) == 1


@pytest.mark.windows
def test_shell_icon_keeps_alpha():
    """Read-only: extract Notepad's icon through IShellItemImageFactory (worker thread, MTA)."""
    import concurrent.futures
    import os

    from PySide6.QtGui import QImage

    from wisp.ui.island.common import _com_init
    from wisp.winapi.shell_icons import icon_png

    path = os.path.join(os.environ["SYSTEMROOT"], "notepad.exe")
    with concurrent.futures.ThreadPoolExecutor(1, initializer=_com_init) as pool:
        png = pool.submit(icon_png, path, 48).result(timeout=20)
    assert png
    image = QImage.fromData(png, "PNG")
    assert image.width() == 48 and image.hasAlphaChannel()
    assert image.pixelColor(0, 0).alpha() < 255  # transparent corner survived


def test_stats_tab_shows_today_and_week(qtbot, db, tmp_path):
    from wisp.settings import SettingsStore
    from wisp.stores.stats import Stats
    from wisp.ui.island.stats_tab import StatsTab, format_duration

    stats = Stats(db, lambda: 40)
    tab = StatsTab(stats, SettingsStore(tmp_path / "s.json"), "#7c5cff")
    qtbot.addWidget(tab)
    stats.record("dictation", words=1200, seconds=300)  # 30 min typing − 5 min speaking
    stats.record("command")
    stats.record("routine")
    tab.refresh()
    assert tab.today.values["words"].text() == "1,200"
    assert tab.today.values["saved"].text() == "25 min"
    assert tab.week.values["commands"].text() == "1"
    assert tab.week.values["routines"].text() == "1"
    assert format_duration(3 * 3600 + 5 * 60) == "3 h 05 min"


def test_stats_tab_survives_restyling(qtbot, db, tmp_path):
    """Regression: an attribute named ``metric`` shadowed QWidget::metric(), so re-applying the
    app stylesheet (every settings save) raised TypeError inside Qt."""
    from PySide6.QtWidgets import QApplication

    from wisp.settings import SettingsStore
    from wisp.stores.stats import Stats
    from wisp.ui import theme
    from wisp.ui.island.stats_tab import StatsTab

    tab = StatsTab(Stats(db, lambda: 40), SettingsStore(tmp_path / "s.json"), "#7c5cff")
    qtbot.addWidget(tab)
    tab.show()
    errors = []
    hook = sys.excepthook
    sys.excepthook = lambda *exc: errors.append(exc)
    try:
        app = QApplication.instance()
        app.setStyleSheet(theme.stylesheet(theme.palette("dark", "#14b8a6")))
        tab.repaint()
    finally:
        app.setStyleSheet("")
        sys.excepthook = hook
    assert errors == []
    assert callable(tab.metric)  # QWidget::metric is no longer shadowed


def test_expand_and_collapse_animate_when_motion_is_on(island, qtbot):
    from wisp.ui import motion
    from wisp.ui.island.island import COLLAPSED, EXPANDED, MARGIN

    motion.force(True)
    # The real pointer may rest where the Island appears; its hover timers must not re-expand
    # or collapse the Island mid-test.
    island._expand_timer.setInterval(3_600_000)
    island._collapse_timer.setInterval(3_600_000)
    island.show()
    island.expand()
    assert island.expanded and island.body.isHidden()  # contents appear after the resize
    assert island._resize_anim is not None
    qtbot.waitUntil(lambda: island.size().width() == EXPANDED[0] + 2 * MARGIN, timeout=2000)
    qtbot.waitUntil(lambda: not island.body.isHidden(), timeout=2000)
    island.collapse()
    qtbot.waitUntil(lambda: island.size().width() == COLLAPSED[0] + 2 * MARGIN, timeout=2000)
    screen = QGuiApplication.primaryScreen().availableGeometry()
    assert abs(island.geometry().center().x() - screen.center().x()) <= 1


def test_reduce_motion_jumps_straight_to_the_end(island):
    from wisp.ui import motion
    from wisp.ui.island.island import EXPANDED, MARGIN

    motion.force(None)
    motion.configure(reduce_motion=True)
    try:
        island.show()
        island.expand()
        assert island.size().width() == EXPANDED[0] + 2 * MARGIN and not island.body.isHidden()
    finally:
        motion.configure(reduce_motion=False)

