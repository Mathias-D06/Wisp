"""D-042…D-044: design tokens, contrast, icons, motion, orb, console rows, chrome."""

from __future__ import annotations

import random
import re
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QSize, Signal
from PySide6.QtGui import QIcon

from wisp.ui import iconset, motion, theme

pytestmark = pytest.mark.qt
SRC = Path(__file__).resolve().parent.parent / "src" / "wisp"


# ----- tokens and contrast ------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["dark", "light"])
def test_text_meets_wcag_aa_on_every_surface(qapp, mode):
    p = theme.palette(mode, theme.ACCENTS["Violet"])
    for text in ("text", "secondary", "muted", "danger", "success", "warning"):
        for surface in ("bg", "surface", "surface2", "hover"):
            ratio = theme.contrast(getattr(p, text), getattr(p, surface))
            assert ratio >= 4.5, f"{mode}: {text} on {surface} is {ratio:.2f}:1"


def test_accent_buttons_are_readable_for_any_accent(qapp):
    rng = random.Random(7)
    accents = list(theme.ACCENTS.values()) + [f"#{rng.randrange(0x1000000):06x}"
                                              for _ in range(200)]
    for accent in accents:
        fill, text = theme.accent_pair(accent)
        assert theme.contrast(text, fill) >= 4.5, (accent, fill, text)


def test_no_hard_coded_colours_outside_the_theme():
    allowed = {"ui/theme.py", "settings.py", "selfcheck.py"}  # tokens; data defaults
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel in allowed:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"#[0-9a-fA-F]{6}\b", line):
                offenders.append(f"{rel}:{number}: {line.strip()}")
    assert offenders == []


def test_type_scale_and_shape_tokens():
    assert (theme.CAPTION, theme.BODY, theme.TITLE, theme.DISPLAY) == (12, 13, 15, 20)
    assert theme.RADIUS_CONTROL == 8 and theme.RADIUS_PANEL == 12
    assert all(v % 4 == 0 for v in theme.SPACE.values())
    assert theme.FONT_TEXT == ["Segoe UI Variable Text", "Segoe UI"]
    assert theme.families(theme.CAPTION)[0] == "Segoe UI Variable Small"
    assert theme.families(theme.TITLE)[0] == "Segoe UI Variable Text"
    assert theme.families(theme.DISPLAY)[0] == "Segoe UI Variable Display"
    assert theme.ui_font(theme.CAPTION).families() == theme.FONT_SMALL


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_type_follows_the_windows_minimums(qapp, isolated_data_dir, mode):
    from wisp.ui.island.island import island_stylesheet

    p = theme.palette(mode, theme.ACCENTS["Violet"])
    for sheet in (theme.stylesheet(p), island_stylesheet(p)):
        for rule in re.findall(r"\{([^{}]*)\}", sheet):
            sizes = [int(s) for s in re.findall(r"font-size:\s*(\d+)px", rule)]
            assert set(sizes) <= {theme.CAPTION, theme.BODY, theme.TITLE, theme.DISPLAY}, rule
            if "font-weight" in rule:  # 14 px is Windows' minimum for Semibold
                assert sizes and min(sizes) >= 14, rule


def test_stylesheet_uses_tinted_icons_from_the_cache(qapp, isolated_data_dir):
    p = theme.palette("dark", "#14b8a6")
    sheet = theme.stylesheet(p)
    assert "image: url(" in sheet and p.accent_fill in sheet
    assert list(theme.icon_cache_dir().glob("check-*.svg"))


# ----- icons -------------------------------------------------------------------------------------
def test_every_icon_exists_and_has_its_licence():
    assert (iconset.ICON_DIR / "LICENSE-lucide.txt").read_text(encoding="utf-8").startswith(
        "ISC License")
    for name, file in iconset.ICONS.items():
        assert (iconset.ICON_DIR / f"{file}.svg").is_file(), name


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0])
def test_icons_render_sharp_at_each_scale(qapp, scale):
    pixmap = iconset.icon("mic", "#ff0000").pixmap(QSize(16, 16), scale)
    assert pixmap.devicePixelRatio() == pytest.approx(scale)
    assert pixmap.width() == round(16 * scale)
    image = pixmap.toImage()
    colours = {image.pixelColor(x, y).name() for x in range(image.width())
               for y in range(image.height()) if image.pixelColor(x, y).alpha() == 255}
    assert colours == {"#ff0000"}  # tinted, with fully opaque stroke pixels


def test_stroke_is_the_same_visual_weight_at_any_size():
    small = iconset.svg_text("mic", "#ffffff", 16)
    large = iconset.svg_text("mic", "#ffffff", 32)
    assert 'stroke-width="2.250"' in small and 'stroke-width="1.125"' in large  # 1.5 px each


def test_disabled_and_checked_icon_colours(qapp):
    engine = iconset.SvgIconEngine("mic", "#111111", "#222222", "#333333")
    assert engine._color(QIcon.Mode.Disabled, QIcon.State.Off) == "#222222"
    assert engine._color(QIcon.Mode.Normal, QIcon.State.On) == "#333333"


def test_app_icon_is_drawn_natively_at_every_size(qapp):
    from PIL import Image

    from wisp.ui.icons import orb_icon

    icon = orb_icon("#7c5cff")
    assert {s.width() for s in icon.availableSizes()} >= {16, 24, 32, 48, 256}
    for size in (16, 24, 32, 48, 256):
        image = icon.pixmap(QSize(size, size), 1.0).toImage()
        assert image.width() == size  # its own drawing, not a scaled copy of another size
        centre = image.pixelColor(size // 2, size // 2)
        assert centre.alpha() == 255 and image.pixelColor(0, 0).alpha() == 0
    ico = Image.open(SRC.parent.parent / "packaging" / "wisp.ico")
    assert {(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)} <= set(ico.info["sizes"])


# ----- motion ------------------------------------------------------------------------------------
def test_motion_follows_setting_and_windows(monkeypatch):
    assert isinstance(motion.system_animations_enabled(), bool)  # the real Windows query
    motion.force(None)
    monkeypatch.setattr(motion, "system_animations_enabled", lambda: True)
    motion.configure(reduce_motion=False)
    assert motion.enabled()
    motion.configure(reduce_motion=True)
    assert not motion.enabled()
    motion.configure(reduce_motion=False)
    monkeypatch.setattr(motion, "system_animations_enabled", lambda: False)
    assert not motion.enabled()  # Windows "Animation effects" off


def test_animate_jumps_to_the_end_without_motion(qtbot):
    from wisp.ui.widgets import ToggleSwitch

    switch = ToggleSwitch("Reduce motion")
    qtbot.addWidget(switch)
    motion.force(False)
    finished = []
    assert motion.animate(switch, b"offset", 0.0, 1.0, finished=lambda: finished.append(1)) \
        is None
    assert switch.offset == 1.0 and finished == [1]


def test_toggle_switch_slides_with_motion(qtbot):
    from wisp.ui.widgets import ToggleSwitch

    switch = ToggleSwitch("Always listening")
    qtbot.addWidget(switch)
    switch.show()
    motion.force(True)
    switch.click()
    assert switch.isChecked() and switch.offset < 1.0  # mid-slide
    qtbot.waitUntil(lambda: switch.offset == 1.0, timeout=1000)
    switch.setChecked(False)  # programmatic: no animation
    assert switch.offset == 0.0


# ----- orb ---------------------------------------------------------------------------------------
def test_orb_timer_runs_only_when_visible_and_moving(qtbot):
    from wisp.ui.orb import FRAME_MS, Orb

    orb = Orb(40, "#7c5cff")
    qtbot.addWidget(orb)
    motion.force(True)
    assert not orb.animating  # not shown yet
    orb.show()
    assert orb.animating and orb._timer.interval() == FRAME_MS["idle"]
    orb.set_state("listening", 0.4)
    assert orb._timer.interval() == FRAME_MS["listening"]
    orb.set_state("error")
    assert not orb.animating  # still states don't animate
    orb.set_state("idle")
    orb.hide()
    assert not orb.animating  # hidden windows cost nothing
    motion.force(False)
    orb.show()
    assert not orb.animating  # reduce motion: drawn once per state change


def test_orb_frames_by_state(qtbot):
    from wisp.ui.orb import Orb

    orb = Orb(40, "#7c5cff")
    qtbot.addWidget(orb)
    motion.force(True)
    glows = [orb.frame(t)[0] for t in (0.0, 1.1, 2.2, 3.4)]
    assert max(glows) - min(glows) > 0.1  # ready breathes slowly
    orb.set_state("listening", 1.0)
    for _ in range(20):
        orb.frame(0.0)
    _glow, scale = orb.frame(0.0)
    assert scale > 1.15  # grows with the level
    orb.set_state("offline")
    assert orb.frame(0.0) == (0.0, 0.92)


# ----- console ------------------------------------------------------------------------------------
class FakeMic:
    muted = False


class FakeVoice(QObject):
    transcript = Signal(str, str, bool, int)
    visual = Signal(str, float, str)

    def __init__(self):
        super().__init__()
        self.mic = FakeMic()
        self.always_listening = False
        self.live_state = "ready"
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args: self.calls.append((name, *args))


@pytest.fixture
def console(qtbot, isolated_data_dir):
    from wisp.ui.console import ConsoleWindow

    voice = FakeVoice()
    window = ConsoleWindow(voice, "#7c5cff")
    qtbot.addWidget(window)
    return window


def test_console_rows_merge_per_turn(console):
    voice = console.voice
    voice.transcript.emit("user", "What time", False, 1)
    voice.transcript.emit("model", "It's", False, 0)
    voice.transcript.emit("user", "What time is it?", True, 1)  # late words, same turn
    voice.transcript.emit("model", "It's 3 pm.", True, 0)
    voice.transcript.emit("notice", "Microphone muted.", True, 0)
    rows = console.view.rows()
    assert [(r.role, r.text, r.final) for r in rows] == [
        ("user", "What time is it?", True), ("model", "It's 3 pm.", True),
        ("notice", "Microphone muted.", True)]
    assert rows[2].icon is not None and not rows[2].icon.pixmap().isNull()


def test_console_retry_shows_only_after_an_error(console):
    console._on_visual("idle", 0.0, "Ready")
    assert console.retry.isHidden()
    console.voice.live_state = "error"
    console._on_visual("error", 0.0, "Google rejected this API key.")
    assert not console.retry.isHidden() and console.status.text().startswith("Google rejected")
    console.retry.click()
    assert ("retry",) in console.voice.calls


def test_console_toggles_and_composer(console):
    console.always.click()
    console.mute.click()
    assert ("set_always_listening", True) in console.voice.calls
    assert ("set_muted", True) in console.voice.calls
    console.sync_toggles(muted=False, always_listening=False)
    assert not console.mute.isChecked() and not console.always.isChecked()
    console.input.setText("what time is it")
    console.send.click()
    assert ("send_text", "what time is it") in console.voice.calls
    console.talk.pressed.emit()
    console.talk.released.emit()
    assert ("talk_pressed",) in console.voice.calls and ("talk_released",) in console.voice.calls


def test_console_trims_old_rows(console, monkeypatch):
    from wisp.ui import chat

    monkeypatch.setattr(chat, "MAX_ENTRIES", 5)
    for n in range(8):
        console.voice.transcript.emit("notice", f"note {n}", True, 0)
    assert len(console._entries) == 5


# ----- HUD and chrome ------------------------------------------------------------------------
def test_hud_tones_come_from_the_palette(qapp):
    from wisp.ui.hud import TONES, tone_color

    p = theme.current()
    expected = {"success": p.success, "warning": p.warning, "danger": p.danger,
                "muted": p.muted, "accent": "#7c5cff"}
    for tone in TONES:
        assert tone_color(tone, "#7c5cff").name() == expected[tone]


def test_hud_ticks_only_while_a_level_is_shown(qtbot):
    from wisp.ui.hud import Hud

    hud = Hud("#7c5cff")
    qtbot.addWidget(hud)
    hud.show_state("Transcribing…", "warning")
    assert not hud._ticker.isActive()
    hud.show_state("Dictating…", "success", lambda: 0.3)
    assert hud._ticker.isActive()
    hud.hide_now()


def test_theme_change_after_widgets_are_deleted(qtbot):
    """Theme hooks are bound to their widgets: deleted widgets drop out, nothing raises."""
    import shiboken6
    from PySide6.QtWidgets import QWidget

    from wisp.ui import chrome
    from wisp.ui.island.common import Chip
    from wisp.ui.transcript import TranscriptView
    from wisp.ui.widgets import IconButton, ToggleSwitch

    window = QWidget()
    chrome.prepare(window)
    chrome.prepare(window)  # once is enough
    assert len(window.findChildren(chrome._ThemeHook)) == 1
    view = TranscriptView()
    view.add_row("notice", "Microphone muted.", True)
    for widget in (window, view, Chip("wifi", "Wi-Fi"), IconButton("mic", "Mute"),
                   ToggleSwitch("x")):
        shiboken6.delete(widget)
    with qtbot.captureExceptions() as exceptions:
        theme.set_current(theme.palette("light", "#14b8a6"))
        theme.set_current(theme.palette("dark", "#7c5cff"))
    assert exceptions == []


def test_chrome_never_fails_and_honours_no_mica(qtbot, monkeypatch):
    from PySide6.QtWidgets import QWidget

    from wisp.ui import chrome
    from wisp.winapi import dwm

    monkeypatch.setenv("WISP_NO_MICA", "1")
    assert not chrome.mica_wanted()
    window = QWidget()
    qtbot.addWidget(window)
    chrome.prepare(window)
    assert not window.property("mica")
    chrome.apply(window)  # dark title + corners where supported; never raises
    applied = dwm.style_window(int(window.winId()), dark=True, backdrop=False)
    assert set(applied) == {"dark_title", "rounded", "mica"}
