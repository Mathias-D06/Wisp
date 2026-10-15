"""Record the island's transitions for docs/island (D-045).

The real Island widget (inside a real WispApp with a throwaway data folder and sample content) is
driven through its own event handlers and rendered frame by frame with QWidget.render on a
simulated clock. Its windows never appear on screen (WA_DontShowOnScreen), so every frame is
exact, no pointer can disturb it and nothing from this PC's screen can end up in an image. GIFs
run at 50 fps: 20 ms is the shortest frame delay GIF viewers honour.

Run: .venv\\Scripts\\python spikes\\island_record.py [OUT_DIR] [--stills | --only NAME] [--dpr 1.0]
"""

from __future__ import annotations

import io
import math
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("WISP_DATA_DIR", tempfile.mkdtemp(prefix="wisp-island-"))
os.environ.setdefault("WISP_NO_MICA", "1")
_DPR = float(sys.argv[sys.argv.index("--dpr") + 1]) if "--dpr" in sys.argv else 1.0
# Render at an exact scale whatever this PC's own scaling is (as spikes/render_ui.py --dpr).
import ctypes  # noqa: E402

ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
os.environ["QT_SCALE_FACTOR"] = f"{_DPR / (ctypes.windll.user32.GetDpiForSystem() / 96):.4f}"

from PIL import Image  # noqa: E402
from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

FPS = 50
WALL0 = 1_800_000_000.0


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeMeter:
    """A music-like peak level, so the equaliser moves in the recording."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def peak(self) -> float:
        t = self.clock.now
        return 0.45 + 0.3 * math.sin(t * 7.1) * math.sin(t * 2.3 + 1) + 0.15 * math.sin(t * 17)


def sample_art() -> bytes:
    """A made-up album cover: a soft two-colour gradient."""
    image = Image.new("RGB", (96, 96))
    for y in range(96):
        for x in range(96):
            image.putpixel((x, y), (40 + x, 60 + y // 2, 150 + (x + y) // 4))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def gif_palette(frames: list[Image.Image]) -> Image.Image:
    """One palette for the whole recording. Median cut (Pillow's default) keeps gradients smooth
    but merges small areas of colour, such as calendar dots, into their neighbours; fast octree
    keeps those. So: 232 median-cut colours plus the octree colours furthest from all of them."""
    picks = frames[:: max(1, len(frames) // 12)]
    sheet = Image.new("RGB", (frames[0].width, frames[0].height * len(picks)))
    for index, frame in enumerate(picks):
        sheet.paste(frame, (0, frame.height * index))

    def colours(image: Image.Image, count: int) -> list[tuple[int, ...]]:
        flat = image.getpalette()[: count * 3]
        return [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]

    base = colours(sheet.quantize(232, Image.Quantize.MEDIANCUT), 232)
    octree = colours(sheet.quantize(255, Image.Quantize.FASTOCTREE), 255)

    def gap(colour: tuple[int, ...]) -> int:
        return min(sum((a - b) ** 2 for a, b in zip(colour, other, strict=True)) for other in base)

    extra = sorted(octree, key=gap, reverse=True)[:23]
    palette = Image.new("P", (1, 1))
    palette.putpalette([value for colour in base + extra for value in colour])
    return palette


class Recorder:
    def __init__(self, out: Path) -> None:
        from wisp.app import WispApp
        from wisp.ui import motion

        self.out = out
        self.app = QApplication.instance() or QApplication(sys.argv[:1])
        motion.force(True)
        self.wisp = WispApp(self.app, background=True)
        self.island = island = self.wisp.island
        self.clock = Clock()
        island.clock = self.clock
        island.wall = lambda: WALL0 + self.clock.now
        island.machine.clock = self.clock
        island.meter = FakeMeter(self.clock)
        island._poll.stop()  # no full-screen checks against the real desktop
        for timer in (island._hold, island._leave, island._outside, island._deadline):
            timer.stop()
        for widget in (island, island.shadow):
            widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        island.enabled = True
        island.show()
        island._frame.stop()
        self.frames: list[Image.Image] = []
        self.backdrop = self._backdrop()
        chat = island.panel.chat
        chat.add("user", "What's on my calendar this afternoon?", True, 1)
        chat.add("model", "You have a dentist appointment at 3 pm and a call with Ana at 4.",
                 True)

    def _backdrop(self) -> QImage:
        size = self.island.size() * self.island.devicePixelRatioF()
        image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(self.island.devicePixelRatioF())
        painter = QPainter(image)
        gradient = QLinearGradient(0, 0, self.island.width(), self.island.height())
        gradient.setColorAt(0.0, QColor("#7a8ba3"))
        gradient.setColorAt(1.0, QColor("#c9b8a6"))
        painter.fillRect(QRect(QPoint(0, 0), self.island.size()), gradient)
        painter.end()
        return image

    # ----- driving ------------------------------------------------------------------------------
    def voice(self, state: str, text: str = "", level: float = 0.0) -> None:
        self.island._on_visual(state, level, text)

    def advance(self, seconds: float, each=None) -> None:
        for _ in range(max(1, round(seconds * FPS))):
            self.clock.now += 1 / FPS
            if each is not None:
                each(self.clock.now)
            self.island.machine.update()
            self.island._tick()
            self.app.processEvents()
            self.frames.append(self.capture())

    def capture(self, crop: QRect | None = None) -> Image.Image:
        island = self.island
        image = QImage(self.backdrop)
        painter = QPainter(image)
        if island.shadow.isVisible():
            island.shadow.render(painter, QPoint(), renderFlags=QWidget.RenderFlag.DrawChildren)
        island.render(painter, QPoint(), renderFlags=QWidget.RenderFlag.DrawChildren)
        if getattr(self, "annotate", None) is not None:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.annotate(painter)  # recording-only marks (the reveal zone, a pointer)
        painter.end()
        image = image.convertToFormat(QImage.Format.Format_RGB888)
        pil = Image.frombuffer("RGB", (image.width(), image.height()),
                               bytes(image.constBits()), "raw", "RGB", image.bytesPerLine(), 1)
        return pil.copy()

    def save_gif(self, name: str, height: int | None = None) -> Path:
        frames = self.frames
        if height is not None:
            ratio = self.island.devicePixelRatioF()
            frames = [f.crop((0, 0, f.width, int(height * ratio))) for f in frames]
        path = self.out / f"{name}.gif"
        palette = gif_palette(frames)
        frames = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=1000 // FPS,
                       loop=0, optimize=True, disposal=1)
        self.frames = []
        print(f"saved {path} ({len(frames)} frames)")
        return path

    def still(self, name: str, height: int | None = None) -> None:
        frame = self.capture()
        if height is not None:
            frame = frame.crop((0, 0, frame.width, int(height * self.island.devicePixelRatioF())))
        frame.save(self.out / f"{name}.png")

    def settle(self) -> None:
        self.advance(1.0)
        self.frames = []

    # ----- the recordings ----------------------------------------------------------------------
    def voice_flow(self) -> None:
        """idle → listening → thinking → speaking → idle."""
        self.settle()
        self.advance(0.5)
        self.island._on_transcript("user", "", False, 2)
        self.voice("listening", "Listening…", 0.2)

        def talk(t):
            self.voice("listening", "Listening…", 0.25 + 0.2 * abs(math.sin(t * 6.3)))

        self.advance(1.6, talk)
        self.voice("thinking", "Thinking…")
        self.advance(1.2)
        reply = "It's 2:40 pm. Your dentist appointment is in twenty minutes."
        self.island._on_transcript("model", reply, False, 0)

        def speak(t):
            self.voice("speaking", "Speaking", 0.3 + 0.25 * abs(math.sin(t * 8.1)))

        self.advance(2.0, speak)
        self.voice("idle", "Ready")
        self.advance(1.0)
        self.save_gif("voice_flow", height=150)

    def split(self) -> None:
        """Music, then voice while the music plays: the island splits."""
        from wisp.system.media import MediaState

        self.settle()
        self.island.show_media(MediaState(True, "Weightless", "Marconi Union", "Spotify", True,
                                          95, 480, sample_art()))
        self.advance(1.4)
        self.voice("listening", "Listening…", 0.3)
        self.advance(2.0, lambda t: self.voice("listening", "Listening…",
                                               0.25 + 0.2 * abs(math.sin(t * 6.3))))
        self.voice("idle", "Ready")
        self.advance(1.2)
        self.save_gif("split_music_and_voice", height=150)
        self.island.show_media(MediaState())
        self.settle()

    def banner(self) -> None:
        """A routine finishes: banner, then back to idle by itself."""
        self.settle()
        self.advance(0.4)
        self.island.notify("Routine done: Morning apps", "✓ Opened Unity Hub\n✓ Opened Spotify")
        self.advance(4.2)
        self.save_gif("banner_routine_done", height=170)

    def expand_collapse(self) -> None:
        """Hover (slight grow), hold to expand, then collapse."""
        self.settle()
        self.advance(0.3)
        self.island._set_hover(True)
        self.advance(0.35)
        self.island.expand()
        self.advance(1.4)
        self.island._set_hover(False)
        self.island.collapse()
        self.advance(1.0)
        self.save_gif("expand_and_collapse")

    def interrupt(self) -> None:
        """Expanding, interrupted half-way by a collapse: it turns smoothly, no jump."""
        self.settle()
        self.advance(0.2)
        self.island.expand()
        self.advance(0.16)
        self.island.collapse()
        self.advance(0.9)
        self.save_gif("interrupted_expand")

    def autohide_reveal(self) -> None:
        """Idle for a moment, slides up and fades away; the pointer (drawn) rests in the
        top-centre zone (dashed) and the island comes back."""
        from PySide6.QtGui import QPen

        from wisp.ui.island.reveal import hot_zone

        island = self.island
        island.configure("primary", hide_when_idle=True, hide_after_s=3)
        self.settle()
        self.annotate = None
        self.advance(3.4)  # the quiet spell, then the slide
        canvas_zone = hot_zone(QRect(0, 0, island.width(), island.height()))  # canvas coords
        pointer = [QPoint(island.width() // 2 + 160, 90)]

        def draw(painter: QPainter) -> None:
            pen = QPen(QColor(255, 255, 255, 200), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(canvas_zone.adjusted(0, 0, 0, 4))
            tip = pointer[0]
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawPolygon([tip, tip + QPoint(0, 16), tip + QPoint(4, 12),
                                 tip + QPoint(8, 19), tip + QPoint(10, 18), tip + QPoint(7, 11),
                                 tip + QPoint(12, 11)])

        self.annotate = draw
        start, end = QPoint(pointer[0]), QPoint(island.width() // 2, 1)
        steps = 30
        for step in range(steps):  # the pointer travels to the zone
            t = (step + 1) / steps
            pointer[0] = QPoint(round(start.x() + (end.x() - start.x()) * t),
                                round(start.y() + (end.y() - start.y()) * t))
            self.advance(1 / 50)
        self.advance(0.16)  # rests there for the dwell
        island.machine.reveal()
        island._apply_visibility()
        self.advance(1.6)
        self.annotate = None
        self.save_gif("autohide_and_reveal", height=150)
        island.configure("primary", hide_when_idle=False)

    def calendar_tab(self) -> None:
        """The Calendar tab with a made-up calendar: agenda, month view, a day picked."""
        from datetime import timedelta

        import sample_calendar

        from wisp.ui.island.calendar_tab import CalendarTab

        sample_calendar.fill(self.wisp.calendar)
        island = self.island
        panel = island.panel
        index = next(i for i, (name, _w) in enumerate(panel.tabs) if name == "Calendar")
        tab = next(w for _name, w in panel.tabs if isinstance(w, CalendarTab))
        self.settle()
        island.expand()
        self.advance(0.6)
        panel.show_tab(index)
        self.advance(2.0)
        tab.views.button(1).click()
        self.advance(1.6)
        tab.grid.selected = tab.grid.today + timedelta(days=3)
        tab.grid.update()
        tab._fill_day()
        self.advance(1.8)
        tab.views.button(0).click()
        self.advance(1.0)
        self.save_gif("calendar_tab")
        island.collapse()
        self.settle()

    def wait_real(self, seconds: float) -> None:
        """Let background work that runs in real time (shell thumbnails) finish."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.02)

    def files_tab(self) -> None:
        """The Files & Share tab with made-up files: a file dropped on the island lands on the
        shelf, Downloads, a search, then the phone link (QR code, a file from the phone to
        accept) and the island's "Phone link" countdown once collapsed."""
        import sample_files

        island = self.island
        tab, phone, (_documents, downloads) = sample_files.install(
            self.wisp, wall=lambda: WALL0 + self.clock.now)
        index = next(i for i, (name, _w) in enumerate(island.panel.tabs)
                     if name == "Files & Share")
        tab._fill_places()
        tab.lists.button(1).click()  # ask for every icon and thumbnail up front
        tab.add_to_shelf([downloads / "mountain-lake.png"])
        self.wait_real(2.5)
        tab.shelf.remove(downloads / "mountain-lake.png")
        tab.lists.button(0).click()
        self.settle()
        island.expand()
        self.advance(0.6)
        island.panel.show_tab(index)
        self.advance(1.4)
        island.files_dropped.emit([downloads / "mountain-lake.png"])
        self.advance(1.2)
        tab.lists.button(1).click()
        self.advance(1.2)
        tab.search.setText("report")
        tab._run_search()
        self.advance(1.6)
        tab.search.clear()
        phone.start([downloads / "invoice-0912.pdf"])
        self.advance(1.4)
        phone.ask("IMG_2041.jpg", 3_400_000)
        self.advance(1.6)
        phone.accept(phone.waiting[0])
        self.advance(0.6)
        island.collapse()
        self.advance(1.8)
        self.save_gif("files_and_share")
        phone.stop()
        self.settle()

    def screen_assist(self) -> None:
        """Screen Assist with a made-up window and scripted answers (spikes/sample_screen.py):
        asking, a quick look, Review with a code fix, then Watch mode's indicator."""
        import sample_screen

        from wisp.ui.island.assist_tab import AssistTab

        island = self.island
        tab = next(w for _name, w in island.panel.tabs if isinstance(w, AssistTab))
        index = next(i for i, (name, _w) in enumerate(island.panel.tabs) if name == "Screen")
        quick, review = sample_screen.exchanges()
        self.settle()
        level = [0.0]
        self.wisp.feedback.show_state("Listening… release to ask", "accent",
                                      lambda: level[0])
        self.advance(1.4, lambda t: level.__setitem__(0, 0.35 + 0.3 * math.sin(t * 9)))
        self.wisp.feedback.show_state("Looking…", "warning")
        self.advance(0.8)
        self.wisp.feedback.hide_now()
        island.panel.show_tab(index)
        tab.show_exchange(quick)
        island.expand()
        self.advance(2.6)
        tab.show_exchange(review)
        self.advance(2.8)
        island.machine.set_watching("Watching", WALL0 + self.clock.now + 30 * 60)
        island.collapse()
        self.advance(1.4)
        island._cursor_inside = lambda: True  # the drawn pointer rests on it: "Stop" shows
        island._set_hover(True)
        self.advance(0.8)
        island._set_hover(False)
        del island._cursor_inside
        self.advance(0.6)
        self.save_gif("screen_assist")
        island.machine.set_watching(None)
        self.settle()

    def stills(self) -> None:
        from wisp.system.media import MediaState

        self.settle()
        self.still("idle", 120)
        for state, text, level in (("listening", "Listening…", 0.5), ("thinking", "Thinking…", 0),
                                   ("speaking", "Speaking", 0.5)):
            self.voice(state, text, level)
            if state == "speaking":
                self.island._on_transcript("model", "It's 2:40 pm. Your dentist is at 3.", False)
            self.settle()
            self.still(state, 120)
        self.voice("idle", "Ready")
        self.island.show_media(MediaState(True, "Weightless", "Marconi Union", "Spotify", True,
                                          95, 480, sample_art()))
        self.settle()
        self.still("music", 120)
        self.voice("listening", "Listening…", 0.4)
        self.settle()
        self.still("split", 120)
        self.voice("idle", "Ready")
        self.island.show_media(MediaState())
        self.island.machine.set_countdown("Call the dentist", WALL0 + self.clock.now + 272)
        self.settle()
        self.still("countdown", 120)
        self.island.machine.set_countdown(None)
        self.wisp.feedback.show_state("Dictating… release to insert", "success", lambda: 0.4)
        self.settle()
        self.still("dictation", 120)
        self.wisp.feedback.hide_now()
        self.island.notify("Reminder", "Call the dentist (due 15:00)")
        self.settle()
        self.still("banner", 140)
        self.island.machine.dismiss()
        self.island.expand()
        self.settle()
        self.still("expanded")
        self.island.collapse()
        self.settle()


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for option in ("--dpr", "--only"):
        if option in sys.argv:
            args = [a for a in args if a != sys.argv[sys.argv.index(option) + 1]]
    out = Path(args[0] if args else "spikes/out/island")
    out.mkdir(parents=True, exist_ok=True)
    recorder = Recorder(out)
    if "--stills" in sys.argv:
        recorder.stills()
    elif "--only" in sys.argv:  # one recording by name, e.g. --only autohide_reveal
        getattr(recorder, sys.argv[sys.argv.index("--only") + 1])()
    else:
        recorder.voice_flow()
        recorder.split()
        recorder.banner()
        recorder.expand_collapse()
        recorder.interrupt()
        recorder.autohide_reveal()
        recorder.calendar_tab()
        recorder.files_tab()
        recorder.screen_assist()
    recorder.wisp.quit()


if __name__ == "__main__":
    main()
