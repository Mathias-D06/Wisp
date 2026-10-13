from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from PIL import Image
from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, Signal

from wisp.ui.overlay import map_to_pixmap

pytestmark = pytest.mark.qt


# ----- coordinate mapping -------------------------------------------------------------------
@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0])
def test_map_to_pixmap_scales(scale):
    geometry = QRect(0, 0, 1000, 800)
    pix_w, pix_h = int(1000 * scale), int(800 * scale)
    rect = map_to_pixmap(QRectF(100, 200, 300, 100), geometry, pix_w, pix_h)
    assert rect == QRect(int(100 * scale), int(200 * scale), round(300 * scale),
                         round(100 * scale))


def test_map_to_pixmap_secondary_monitor_left_of_primary():
    geometry = QRect(-1536, 120, 1536, 864)  # 1920x1080 at 125 % to the left of primary
    rect = map_to_pixmap(QRectF(-1436, 220, 200, 100), geometry, 1920, 1080)
    assert rect == QRect(125, 125, 250, 125)


def test_map_to_pixmap_clamps_to_image():
    rect = map_to_pixmap(QRectF(-50, -50, 200, 200), QRect(0, 0, 100, 100), 100, 100)
    assert rect == QRect(0, 0, 100, 100)


# ----- overlay --------------------------------------------------------------------------------
class FakeScreen:
    def __init__(self, geometry: QRect):
        self._geometry = geometry

    def geometry(self) -> QRect:
        return self._geometry


DEFAULT_GEOMETRY = (0, 0, 400, 300)


def _overlay(qtbot, scale=2.0, geometry=None):
    geometry = geometry or QRect(*DEFAULT_GEOMETRY)
    from PySide6.QtGui import QColor, QPixmap

    from wisp.ui.overlay import CircleOverlay

    shot = QPixmap(int(geometry.width() * scale), int(geometry.height() * scale))
    shot.fill(QColor("#336699"))
    overlay = CircleOverlay(FakeScreen(geometry), shot, "#7c5cff")
    qtbot.addWidget(overlay)
    return overlay


def _draw_loop(qtbot, overlay, points):
    from PySide6.QtTest import QTest

    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(*points[0]))
    for x, y in points[1:]:
        QTest.mouseMove(overlay, QPoint(x, y))
        overlay.strokes[-1].append(overlay.mapFromGlobal(overlay.mapToGlobal(QPoint(x, y)))
                                   .toPointF())
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       QPoint(*points[-1]))


def test_overlay_crop_uses_physical_pixels(qtbot):
    overlay = _overlay(qtbot, scale=2.0)
    _draw_loop(qtbot, overlay, [(100, 100), (200, 100), (200, 150), (100, 150), (100, 100)])
    assert overlay.has_stroke()
    box = overlay.local_bbox()
    assert box == QRectF(88, 88, 124, 74)  # loop bounds plus 12 px padding
    jpeg, anchor = overlay.crop()
    image = Image.open(io.BytesIO(jpeg))
    assert image.format == "JPEG" and image.size == (248, 148)  # 2x physical pixels
    assert anchor == QRect(88, 88, 124, 74)


def test_overlay_without_loop_has_no_crop(qtbot):
    overlay = _overlay(qtbot)
    assert not overlay.has_stroke() and overlay.crop() is None


@pytest.mark.windows
def test_real_screens_grab_at_physical_resolution(qtbot):
    from PySide6.QtGui import QGuiApplication

    for screen in QGuiApplication.screens():
        shot = screen.grabWindow(0)
        assert not shot.isNull()
        ratio = shot.width() / screen.geometry().width()
        assert abs(ratio - screen.devicePixelRatio()) < 0.05, (ratio, screen.devicePixelRatio())


# ----- controller -----------------------------------------------------------------------------
class FakeVoice(QObject):
    transcript = Signal(str, str, bool, int)

    def __init__(self, always=False):
        super().__init__()
        self.always_listening = always
        self.suspended = []
        self.talking = False
        self.awaiting_reply = False

    def suspend_always(self, flag):
        self.suspended.append(flag)


class FakeLive:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name, *[len(a) if isinstance(a, bytes) else a
                                                         for a in args]))


class FakeMic:
    level = 0.1

    def __init__(self):
        self.subs = {}
        self.users = set()

    def acquire(self, user):
        self.users.add(user)

    def release(self, user):
        self.users.discard(user)

    def subscribe(self, name, cb):
        self.subs[name] = cb

    def unsubscribe(self, name):
        self.subs.pop(name, None)


class FakeOverlay:
    def __init__(self, screen, shot, accent, stroke=True):
        self.stroke = stroke
        self.shown = False

    def show(self):
        self.shown = True

    def raise_(self):
        return None

    def hide(self):
        self.shown = False

    def deleteLater(self):
        return None

    def has_stroke(self):
        return self.stroke

    def crop(self):
        return (b"JPEGDATA", QRect(10, 10, 50, 50)) if self.stroke else None


class FakeBubble:
    def __init__(self):
        self.texts = []
        self.finished = None

    def show_at(self, anchor, text):
        self.texts.append(text)

    def set_text(self, text):
        self.texts.append(text)

    def finish(self, seconds=0.0):
        self.finished = seconds


def make_controller(always=False, stroke=True):
    from wisp.circle import CircleController

    voice, live, mic, bubble = FakeVoice(always), FakeLive(), FakeMic(), FakeBubble()
    hud = SimpleNamespace(show_state=lambda *a: None, flash=lambda *a: None,
                          hide_now=lambda: None)
    screen = SimpleNamespace(grabWindow=lambda wid: "SHOT")
    controller = CircleController(
        voice, live, mic, hud, bubble, has_key=lambda: True, accent=lambda: "#7c5cff",
        screens=lambda: [screen, screen],
        overlay_factory=lambda s, shot, accent: FakeOverlay(s, shot, accent, stroke),
    )
    return controller, voice, live, mic, bubble


def names(live):
    return [c[0] for c in live.calls]


def test_push_to_talk_flow_sends_image_before_closing_turn(qtbot):
    controller, voice, live, mic, bubble = make_controller()
    controller.on_hotkey("circle", "press")
    assert len(controller.overlays) == 2 and all(o.shown for o in controller.overlays)
    assert names(live) == ["begin_turn"]
    mic.subs["circle"](b"\x00\x00" * 512)  # the question streams live during the gesture
    assert names(live) == ["begin_turn", "push_audio"]
    controller.on_hotkey("circle", "release")
    assert names(live) == ["begin_turn", "push_audio", "send_image"]
    qtbot.waitUntil(lambda: "end_turn" in names(live), timeout=2000)
    assert names(live) == ["begin_turn", "push_audio", "send_image", "end_turn"]
    assert not mic.users and voice.awaiting_reply
    voice.transcript.emit("model", "That's a bar chart of", False, 0)
    voice.transcript.emit("model", "That's a bar chart of sales.", True, 0)
    assert bubble.texts[-1] == "That's a bar chart of sales." and bubble.finished == 12.0


def test_always_listening_buffers_and_replays_question(qtbot):
    controller, voice, live, mic, _ = make_controller(always=True)
    controller.begin()
    assert voice.suspended == [True] and "begin_turn" not in names(live)
    mic.subs["circle"](b"\x01\x00" * 3000)
    controller.finish()
    qtbot.waitUntil(lambda: "audio_stream_end" in names(live), timeout=2000)
    sent = names(live)
    assert sent[0] == "send_image" and sent[-1] == "audio_stream_end"
    assert sent.count("push_audio") == 6  # 6000 bytes in 1024-byte chunks
    assert voice.suspended == [True, False]


def test_nothing_circled_cancels_turn(qtbot):
    controller, _voice, live, _mic, bubble = make_controller(stroke=False)
    controller.begin()
    controller.finish()
    assert names(live) == ["begin_turn", "cancel_turn"]
    assert bubble.texts == []


def test_other_key_cancels(qtbot):
    controller, voice, live, mic, _ = make_controller()
    controller.on_hotkey("circle", "press")
    controller.on_hotkey("circle", "cancel")
    assert names(live) == ["begin_turn", "cancel_turn"] and not mic.users
    assert controller.overlays == [] and not voice.talking


@pytest.mark.qt
def test_overlay_loop_is_outlined_not_filled(qtbot):
    """Regression: the hint pill's brush once filled the user's loop and hid what was circled."""
    from PySide6.QtCore import QPointF, QRect
    from PySide6.QtGui import QColor, QPixmap

    from wisp.ui.overlay import CircleOverlay

    class Screen:
        def geometry(self):
            return QRect(0, 0, 400, 300)

    shot = QPixmap(400, 300)
    shot.fill(QColor("#ffffff"))
    overlay = CircleOverlay(Screen(), shot, "#7c5cff")
    qtbot.addWidget(overlay)
    overlay.resize(400, 300)
    import math

    overlay.strokes = [[QPointF(200 + 80 * math.cos(t / 20 * math.tau),
                                180 + 50 * math.sin(t / 20 * math.tau)) for t in range(21)]]
    image = overlay.grab().toImage()
    ratio = image.devicePixelRatio()  # sample in device pixels (e.g. 2 at 200 % scaling)
    centre = image.pixelColor(round(200 * ratio), round(180 * ratio))
    assert centre.lightness() > 150  # the screenshot (dimmed white) shows inside the loop
