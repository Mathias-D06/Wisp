"""Dev helper: render Wisp windows offscreen to PNG files for visual review.

Run: .venv\\Scripts\\python spikes\\render_ui.py [--out DIR] [--docs] [name ...]
Images go to spikes/out/ (or DIR). Uses a temporary data folder so real settings are untouched.
``--docs`` skips the Island's Apps and Wallpaper tabs, which show the PC's own apps and pictures.
``--dpr 1.25`` renders at exactly 125 % display scaling (relative to this PC's own).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("WISP_DATA_DIR", tempfile.mkdtemp(prefix="wisp-render-"))
os.environ.setdefault("WISP_NO_MICA", "1")  # an off-screen grab can't show the desktop material
if "--dpr" in sys.argv:
    # Render at an exact display scaling (1.0 = 100 %) whatever this PC's own scaling is.
    import ctypes

    _target = float(sys.argv[sys.argv.index("--dpr") + 1])
    # Per-monitor-aware first (as Qt will be), otherwise Windows reports a virtualised 96 DPI.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    _system = ctypes.windll.user32.GetDpiForSystem() / 96
    os.environ["QT_SCALE_FACTOR"] = f"{_target / _system:.4f}"
    del sys.argv[sys.argv.index("--dpr"):sys.argv.index("--dpr") + 2]

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

OUT = Path(__file__).parent / "out"
DOCS = False
PERSONAL_TABS = ("Apps", "Wallpaper")


def _sample_data(wisp_app) -> None:
    """Fill a throwaway data folder with realistic items for screenshots."""
    from datetime import datetime, timedelta

    from wisp.scheduling.spec import Schedule

    services = wisp_app.services
    now = datetime.now().astimezone()
    services.scheduler.start()
    tasks = [
        ("Morning apps", Schedule(repeat="weekdays", time="09:00"),
         [{"tool": "open_app", "args": {"name": "Unity Hub"}},
          {"tool": "open_app", "args": {"name": "Spotify"}}]),
        ("Gift wrap search", Schedule(repeat="none", at=(now + timedelta(days=29)).replace(
            hour=11, minute=0).isoformat(timespec="minutes")),
         [{"tool": "web_search", "args": {"query": "gift wraps", "site": "amazon"}}]),
        ("Weekly review", Schedule(repeat="weekly", time="17:30", days=["fri"]),
         [{"prompt": "Summarise my open to-dos"}]),
    ]
    for title, schedule, steps in tasks:
        services.scheduler.schedule(services.tasks.add(title, schedule, steps))
    services.todos.add("Call the dentist", due_at=now.replace(hour=15, minute=0))
    services.todos.add("Buy gift wrap")
    services.todos.add("Send invoice to Ana", due_at=now + timedelta(days=1))
    services.memory.add("My sister Hana's birthday is 3 May", pinned=True)
    services.memory.add("I work from home on Fridays")
    services.memory.add("I prefer metric units and 24-hour times")


def render_settings(app: QApplication) -> None:
    from wisp import paths
    from wisp.app import WispApp

    wisp_app = WispApp(app, background=True)
    _sample_data(wisp_app)
    for page in wisp_app.settings_pages():
        from wisp.ui.settings.dialog import SettingsDialog

        dialog = SettingsDialog(wisp_app.settings_store, [page])
        dialog.resize(780, 640)
        dialog.open_page(page.title)
        app.processEvents()
        dialog.grab().save(str(OUT / f"settings_{page.title.lower().replace(' ', '_')}.png"))
        dialog.close()
    print("data dir", paths.data_dir())


def render_console(app: QApplication) -> None:
    from wisp.app import WispApp
    from wisp.tools.base import Origin

    wisp_app = WispApp(app, background=True)
    console = wisp_app.console
    console.add("user", "Open Spotify and play something chill", True)
    console.add("model", "Opening Spotify now. Want me to search for a lofi playlist?", True)
    console.add("notice", "Microphone muted.", True)
    console.add("user", "yes and turn the volume", False)
    console.resize(560, 520)
    console.show()
    app.processEvents()
    console.grab().save(str(OUT / "console.png"))
    wisp_app.confirmations.create("delete_file", {"path": "C:/x.txt"},
                                  "Move C:\\Users\\me\\report.docx to the Recycle Bin",
                                  Origin.VOICE)
    for _ in range(5):
        app.processEvents()
    wisp_app.confirm_card.grab().save(str(OUT / "confirm_card.png"))
    wisp_app.quit()


def render_circle(app: QApplication) -> None:
    from PySide6.QtCore import QPointF, QRect
    from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap

    from wisp.ui.bubble import AnswerBubble
    from wisp.ui.overlay import CircleOverlay

    class Screen:
        def geometry(self):
            return QRect(0, 0, 900, 500)

    shot = QPixmap(900, 500)
    painter = QPainter(shot)
    gradient = QLinearGradient(0, 0, 900, 500)
    gradient.setColorAt(0, QColor("#dfe7f5"))
    gradient.setColorAt(1, QColor("#f8f1e4"))
    painter.fillRect(shot.rect(), gradient)
    painter.setPen(QColor("#333"))
    painter.drawText(QRect(380, 210, 300, 60), 0, "Quarterly revenue: 4.2M")
    painter.end()
    overlay = CircleOverlay(Screen(), shot, "#7c5cff")
    import math

    loop = [QPointF(520 + 150 * math.cos(t / 20 * math.tau), 235 + 45 * math.sin(t / 20 * math.tau))
            for t in range(21)]
    overlay.strokes = [loop]
    overlay.resize(900, 500)
    overlay.grab().save(str(OUT / "circle_overlay.png"))
    bubble = AnswerBubble()
    bubble.show_at(QRect(370, 190, 300, 90),
                   "That's the quarterly revenue figure: 4.2 million, up from last quarter.")
    app.processEvents()
    bubble.grab().save(str(OUT / "answer_bubble.png"))


def _pump(app: QApplication, seconds: float) -> None:
    import time

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def render_island(app: QApplication) -> None:
    from wisp.app import WispApp
    from wisp.system.media import MediaState

    wisp_app = WispApp(app, background=True)
    _sample_data(wisp_app)
    services = wisp_app.services
    services.clipboard.add_text("Meeting notes: launch review moved to Thursday 3pm")
    services.clipboard.add_text("https://example.org/quarterly-report")
    services.stats.record("dictation", words=180, seconds=60)
    services.stats.record("command")
    services.stats.record("routine")
    services.app_index.refresh()
    island = wisp_app.island
    island._poll.stop()  # no full-screen checks against the real desktop
    for widget in (island, island.shadow):  # never on screen: no pointer can hover it
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    island.enabled = True
    island.show()
    island.show_media(MediaState(True, "Weightless", "Marconi Union", "Spotify", True, 95, 480))
    _pump(app, 0.3)
    island.grab().save(str(OUT / "island_collapsed.png"))
    island.expand()
    for index, (name, _widget) in enumerate(island.panel.tabs):
        if DOCS and name in PERSONAL_TABS:
            continue
        island.panel.show_tab(index)
        _pump(app, 2.0 if name in ("Controls", "Apps", "Wallpaper") else 0.4)
        island.grab().save(str(OUT / f"island_{name.lower()}.png"))
    wisp_app.quit()


RENDERERS = {"settings": render_settings, "console": render_console, "circle": render_circle,
             "island": render_island}


def main() -> None:
    global OUT, DOCS
    args = sys.argv[1:]
    if "--out" in args:
        index = args.index("--out")
        OUT = Path(args[index + 1])
        del args[index:index + 2]
    if "--docs" in args:
        DOCS = True
        args.remove("--docs")
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    from wisp.ui import motion

    motion.force(False)  # grab final states, not the first frame of a fade
    names = args or list(RENDERERS)
    for name in names:
        RENDERERS[name](app)
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
