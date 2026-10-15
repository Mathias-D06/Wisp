"""D-053: Discreet mode. The switch and its calendar schedule, the island's line or dot (grey,
no glow, a corner, its own reveal zone, banners as a pulse except errors), the answer card
(readable: WCAG AA at the default opacity), text-only replies and push-to-talk only, the voice
tool and settings, and the acceptance case: a whole Screen Assist exchange in Discreet mode
with no sound and only the card, then everything back as before."""

from __future__ import annotations

import logging
import sys
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPainter

from tests.test_island_window import island, show  # noqa: F401  (the island fixture)
from wisp.discreet import DiscreetLook, DiscreetMode
from wisp.settings import Settings, SettingsStore, validate
from wisp.ui import theme
from wisp.ui.theme import ISLAND

pytestmark = pytest.mark.qt
NOW = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)


# ----- the switch and the schedule ----------------------------------------------------------------
class FakeCalendar:
    def __init__(self):
        self.connected = True
        self.items = []

    def events(self, start, end):
        return [e for e in self.items if e.start < end and e.end > start]


def event(event_id, start_min, end_min, all_day=False):
    return SimpleNamespace(id=event_id, start=NOW + timedelta(minutes=start_min),
                           end=NOW + timedelta(minutes=end_min), all_day=all_day)


def test_discreet_switch_is_remembered(qtbot, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    mode = DiscreetMode(store)
    assert not mode.active and mode.look() is None
    with qtbot.waitSignal(mode.changed) as changed:
        mode.set_enabled(True, "hotkey")
    assert changed.args == [True] and store.peek().discreet.enabled
    assert mode.look() == DiscreetLook("line", 0.5, "top-centre")
    assert DiscreetMode(SettingsStore(tmp_path / "settings.json")).active  # next start
    assert mode.toggle() is False and not store.peek().discreet.enabled


def test_discreet_during_calendar_events(qtbot, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    calendar = FakeCalendar()
    clock = [NOW]
    mode = DiscreetMode(store, calendar, now=lambda: clock[0])
    calendar.items = [event("lecture", -10, 50), event("holiday", -600, 1000, all_day=True)]
    mode.check_schedule()
    assert not mode.active  # the setting is off
    store.update(lambda s: setattr(s.discreet, "during_events", True))
    mode.check_schedule()
    assert mode.active and mode.auto and not store.peek().discreet.enabled  # not remembered
    mode.set_enabled(False, "tray")  # off during the lecture: stays off until it ends
    mode.check_schedule()
    assert not mode.active
    clock[0] = NOW + timedelta(minutes=55)
    mode.check_schedule()
    assert not mode.active
    calendar.items.append(event("seminar", 60, 120))
    clock[0] = NOW + timedelta(minutes=61)
    mode.check_schedule()
    assert mode.active  # the next event turns it on again
    clock[0] = NOW + timedelta(minutes=121)
    mode.check_schedule()
    assert not mode.active
    calendar.items = [event("holiday", -600, 1000, all_day=True)]
    mode.check_schedule()
    assert not mode.active  # all-day events don't count


# ----- the island ---------------------------------------------------------------------------------
def render(island_widget) -> QImage:
    image = QImage(island_widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    island_widget.paint_island(painter, island_widget.clock())
    painter.end()
    return image


def settle(island_widget) -> None:
    for _ in range(5):
        island_widget.fake.now += 0.05
        island_widget.machine.update()
        island_widget._tick()


def test_island_becomes_a_grey_line_and_comes_back(island):  # noqa: F811
    normal_size = (island.springs["w"], island.springs["h"])
    normal_x = island.x()
    island.set_discreet(DiscreetLook("line", 0.5, "top-centre"))
    settle(island)
    assert (island.springs["w"], island.springs["h"]) == ISLAND.discreet_line
    assert island.machine.calm and not island._moving()
    image = render(island)
    centre = island._main.center().toPoint()
    pixel = QColor.fromRgba(image.pixel(centre))
    grey = QColor(theme.DISCREET_GREY)
    assert abs(pixel.alpha() - 128) <= 3  # 50 % opacity
    assert abs(pixel.red() * 255 / max(1, pixel.alpha()) - grey.red()) <= 4  # grey, no accent
    assert QColor.fromRgba(image.pixel(centre.x(), centre.y() + 12)).alpha() == 0  # no glow
    island.set_discreet(DiscreetLook("dot", 0.5, "top-centre"))
    settle(island)
    assert (island.springs["w"], island.springs["h"]) == ISLAND.discreet_dot
    island.set_discreet(None)
    settle(island)
    assert (island.springs["w"], island.springs["h"]) == normal_size and island.x() == normal_x
    assert not island.machine.calm and island._moving() == __import__(
        "wisp.ui.motion", fromlist=["enabled"]).enabled()


def test_corner_position_reveal_zone_and_hit_area(island):  # noqa: F811
    from wisp.ui.island import geometry
    from wisp.ui.island.reveal import hot_zone

    show(island)
    island.set_discreet(DiscreetLook("line", 0.5, "top-left"))
    screen = island._screen.geometry()
    centre = island.x() + island.width() // 2
    expected = screen.x() + ISLAND.discreet_corner_margin + ISLAND.discreet_line[0] / 2
    assert abs(centre - expected) <= 1
    zone = hot_zone(screen, centre_x=centre, shape_width=ISLAND.discreet_line[0])
    assert zone.left() == screen.x() and zone.top() == screen.y()  # clamped to the screen
    assert zone.contains(QPoint(centre, screen.y()))
    island.set_discreet(DiscreetLook("line", 0.5, "top-right"))
    centre = island.x() + island.width() // 2
    assert abs(centre - (screen.x() + screen.width() - ISLAND.discreet_corner_margin
                         - ISLAND.discreet_line[0] / 2)) <= 1
    island.expand()
    settle(island)
    middle = screen.x() + screen.width() / 2
    assert abs(island.x() + island.width() / 2 - middle) <= 1  # open: the top centre
    island.collapse()
    settle(island)
    assert island.x() + island.width() // 2 > screen.x() + screen.width() // 2
    small = geometry.input_region(island._main, None, grow=ISLAND.discreet_hit_margin)
    assert small.boundingRect().height() >= ISLAND.discreet_line[1] + 2 * \
        ISLAND.discreet_hit_margin


def test_banners_become_a_pulse_but_errors_still_open(island):  # noqa: F811
    show(island)
    island.machine.post("Routine done: Morning apps", "✓")
    island.set_discreet(DiscreetLook())
    assert island.machine._queue == [] and island.machine._showing is None  # dropped
    settle(island)
    assert island.frame_interval(island.clock()) is None  # a still line costs nothing
    island.notify("Reminder", "Call the dentist")
    assert island.machine._queue == [] and island._pulse_until > island.clock()
    assert island.frame_interval(island.clock()) == 33  # the pulse animates
    island.notify("Problem", "Gemini is busy, try again")
    machine = island.machine
    banner = machine._showing or (machine._queue[0] if machine._queue else None)
    assert banner is not None and banner.icon == "warning"  # errors still open up


def test_watch_and_phone_indicators_stay_visible(island):  # noqa: F811
    island.set_discreet(DiscreetLook("line", 0.5, "top-centre"))
    island.machine.set_watching("Watching", 1.8e9 + 1800)
    settle(island)
    image = render(island)
    main = island._main
    dot = QColor.fromRgba(image.pixel(int(main.right() + 7), int(main.center().y())))
    assert dot.alpha() > 200 and dot.red() > dot.blue()  # the amber dot, fully opaque


# ----- the card -----------------------------------------------------------------------------------
def test_card_text_meets_wcag_aa_at_the_default_opacity():
    from wisp.settings import DiscreetSettings

    alpha = DiscreetSettings().card_opacity / 100
    for behind in ("#ffffff", "#000000", "#ffff00", "#7c5cff"):
        background = theme.composite(theme.DISCREET_CARD, alpha, behind)
        assert theme.contrast(theme.DISCREET_CARD_TEXT, background) >= 4.5, behind
        assert theme.contrast(theme.DISCREET_CARD_MUTED, background) >= 4.5, behind
    lowest = theme.composite(theme.DISCREET_CARD, 0.85, "#ffffff")  # the setting's minimum
    assert theme.contrast(theme.DISCREET_CARD_MUTED, lowest) >= 4.5


def test_card_fades_unless_hovered_and_never_opens_links(qtbot):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QEnterEvent

    from wisp.ui.discreet_card import DiscreetCard

    card = DiscreetCard()
    qtbot.addWidget(card)
    card.configure(15, 0.92, 12)
    card.show_text("The build failed: see [the log](https://example.com/run-me).",
                   QPoint(400, 40), kind="screen", openable=True)
    assert card.isVisible() and card._fade.isActive() and card._fade.interval() == 12_000
    assert not card.label.openExternalLinks()
    assert not card.label.textInteractionFlags() & Qt.TextInteractionFlag.LinksAccessibleByMouse
    assert card.open_button.isVisible() and "15px" in card.styleSheet()
    card.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(405, 45)))
    assert not card._fade.isActive()  # stays while hovered
    card.leaveEvent(QEvent(QEvent.Type.Leave))
    assert card._fade.isActive()
    with qtbot.waitSignal(card.speak_requested) as spoken:
        card.speak_button.click()
    assert spoken.args[0].startswith("The build failed")
    card.show_text("partial reply…", QPoint(400, 40), kind="voice", final=False)
    assert not card._fade.isActive()  # still streaming
    card.dismiss()
    assert not card.isVisible() and card.text == ""


# ----- sound and the microphone -------------------------------------------------------------------
def test_replies_are_text_only_but_speak_it_still_plays():
    from wisp.audio.playback import Player

    player = Player(lambda: "")
    player._ensure_stream = lambda: None  # no speaker in tests
    reply, asked = bytes([1, 0]) * 10, bytes([2, 0]) * 10
    try:
        player.muted = True
        player.feed(reply)
        assert len(player._buffer) == 0  # the voice session's reply is dropped
        player.feed(asked, force=True)
        assert bytes(player._buffer) == asked  # "Speak it" still plays
    finally:
        player.close()


def test_always_listening_pauses_while_discreet(qtbot, tmp_path):
    from tests.test_voice import make

    voice, _live, mic, *_ = make(tmp_path)
    voice.set_always_listening(True)
    assert voice.always_listening and "always" in mic.users
    voice.set_discreet(True)
    assert not voice.always_listening and "always" not in mic.users
    assert voice.settings_store.peek().audio.always_listening  # the setting is untouched
    voice.set_discreet(False)
    assert voice.always_listening and "always" in mic.users


# ----- settings and the voice tool ----------------------------------------------------------------
def test_discreet_settings_and_their_page(qtbot):
    from wisp.ui.settings.discreet_page import DiscreetPage

    settings = Settings()
    assert settings.hotkeys.discreet == "ctrl+alt+d" and validate(settings) == []
    d = settings.discreet
    assert (d.style, d.opacity, d.position, d.card_seconds, d.speak_replies, d.mute_toasts) == \
        ("line", 50, "top-centre", 12, False, True)
    bad = Settings()
    bad.discreet.card_opacity = 70
    bad.discreet.position = "bottom"
    problems = validate(bad)
    assert any("85–100" in p for p in problems) and any("top-centre" in p for p in problems)
    page = DiscreetPage()
    qtbot.addWidget(page)
    page.load(settings)
    page.style.setCurrentIndex(page.style.findData("dot"))
    page.position.setCurrentIndex(page.position.findData("top-right"))
    page.speak.setChecked(True)
    page.apply(settings)
    assert (settings.discreet.style, settings.discreet.position, settings.discreet.speak_replies) \
        == ("dot", "top-right", True)
    assert settings.screen_assist.speak_answers  # the normal profile is separate


def test_go_discreet_by_voice():
    from wisp.tools.base import Origin, ToolContext
    from wisp.tools.builtin import discreet

    calls = []
    ctx = ToolContext(Origin.VOICE, SimpleNamespace(
        discreet=SimpleNamespace(set_enabled=lambda on, source: calls.append((on, source)))))
    assert discreet.discreet_mode(ctx, {"on": True})["discreet"] is True
    assert discreet.discreet_mode(ctx, {"on": False})["discreet"] is False
    assert calls == [(True, "voice"), (False, "voice")]


# ----- acceptance: a Screen Assist exchange in Discreet mode --------------------------------------
def test_screen_assist_in_discreet_mode_is_silent_and_only_shows_the_card(
        qtbot, isolated_data_dir, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from tests.test_screen_assist import CODE, FakeModel, FakeSystem, Window, capturer, editor
    from wisp.app import WispApp

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    wisp = WispApp(QApplication.instance(), background=True)
    try:
        model = FakeModel(["A Python file: line 4 uses `quantity`, which isn't defined."])
        wisp.assist.engine.model = model
        wisp.assist.engine.capturer = capturer(FakeSystem(Window(1, "budget.py - Code", "Code"),
                                                          {1: editor(CODE)}))
        fed, toasts = [], []
        from tests.test_screen_assist_ui import FakeMic

        wisp.assist.mic = FakeMic()  # never the real microphone in tests
        wisp.assist.has_key = lambda: True
        monkeypatch.setattr(wisp.player, "feed", lambda pcm, force=False: fed.append(pcm))
        monkeypatch.setattr(wisp.tray, "notify", lambda *args, **kw: toasts.append(args))
        normal = (wisp.island.x(), wisp.player.muted, wisp.voice.discreet)
        wisp.discreet.set_enabled(True, "hotkey")
        with qtbot.waitSignal(wisp.assist.answered, timeout=5000):
            wisp.assist.on_hotkey("screen_assist", "press")
            wisp.assist.on_hotkey("screen_assist", "release")
        qtbot.wait(300)
        assert wisp.discreet_card.isVisible() and "quantity" in wisp.discreet_card.text
        assert not wisp.island.machine.expanded  # the island stays a line
        assert model.spoken == [] and fed == [] and toasts == []  # no sound, no toasts
        wisp._notify("Routine done: Morning apps", "✓")
        assert toasts == [] and wisp.island.machine._queue == []  # a pulse, not a banner
        wisp.discreet.set_enabled(False, "hotkey")
        assert not wisp.discreet_card.isVisible() and wisp.island.discreet is None
        restored = (wisp.island.x(), wisp.player.muted, wisp.voice.discreet)
        assert restored == normal
        assert QRect(wisp.island.geometry()).isValid()
    finally:
        wisp.quit()
        for handler in root.handlers:
            if handler not in handlers:
                handler.close()
        root.handlers[:] = handlers
        root.setLevel(level)
