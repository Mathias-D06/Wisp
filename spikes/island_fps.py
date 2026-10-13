"""Measure the island's frame rate while it morphs, on the real screen (D-045).

Shows the island at the top of the screen, runs expand/collapse, voice and banner transitions
with the real clock, and records when each frame tick of a morph ran and how long each paint
took. A tick can only run after the previous frame was painted and handed to Windows, so
tick-to-tick time is the real frame time. Nothing is read from the screen.
Run: .venv\\Scripts\\python spikes\\island_fps.py
"""

from __future__ import annotations

import os
import statistics
import sys
import tempfile
import time
from itertools import pairwise
from pathlib import Path

os.environ.setdefault("WISP_DATA_DIR", tempfile.mkdtemp(prefix="wisp-fps-"))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main() -> None:
    from wisp.app import WispApp
    from wisp.ui import motion

    app = QApplication(sys.argv[:1])
    motion.force(True)
    wisp = WispApp(app, background=True)
    island = wisp.island
    island._poll.stop()
    island.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    for timer in (island._hold, island._leave, island._outside):
        timer.setInterval(3_600_000)
    island.enabled = True
    island._apply_visibility()

    ticks: list[float] = []
    paints: list[float] = []
    original_tick, original_paint = island._tick, island.paint_island

    def tick() -> None:
        # Only frames of a morph count: once it settles the timer slows down on purpose
        # (30 fps meters, 8 fps idle glow) or stops.
        if island.frame_interval(island.clock()) == 16:
            ticks.append(time.perf_counter())
        original_tick()

    def paint(painter, now) -> None:
        start = time.perf_counter()
        original_paint(painter, now)
        paints.append(time.perf_counter() - start)

    island._frame.timeout.disconnect()
    island._frame.timeout.connect(tick)
    island.paint_island = paint

    def pump(seconds: float) -> None:
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.001)

    results = []

    def measure(label: str, action, seconds: float) -> None:
        pump(0.6)  # settle first
        ticks.clear()
        paints.clear()
        action()
        pump(seconds)
        intervals = [b - a for a, b in pairwise(ticks)]
        if not intervals:
            print(f"{label}: no frames")
            return
        intervals.sort()
        fps = len(intervals) / sum(intervals)
        p95 = intervals[int(len(intervals) * 0.95) - 1] * 1000
        worst = intervals[-1] * 1000
        paint_ms = statistics.mean(paints) * 1000 if paints else 0.0
        results.append((label, fps, p95, worst, paint_ms))
        print(f"{label:<28} {len(intervals):>4} frames  {fps:5.1f} fps  p95 {p95:5.1f} ms"
              f"  worst {worst:5.1f} ms  paint {paint_ms:4.2f} ms")

    for _ in range(2):
        measure("expand (idle -> panel)", island.expand, 0.7)
        measure("collapse (panel -> idle)", island.collapse, 0.7)
    measure("idle -> listening", lambda: island.machine.set_voice("listening", "Listening…"), 0.5)
    measure("listening -> speaking", lambda: island.machine.set_voice("speaking", "Speaking"), 0.5)
    measure("speaking -> idle", lambda: island.machine.set_voice("idle", "Ready"), 0.5)
    measure("banner in", lambda: island.notify("Routine done: Morning apps", "✓ All good"), 0.6)
    measure("banner out", island.machine.dismiss, 0.6)
    morphs = results
    print(f"average over morphs: {statistics.mean(r[1] for r in morphs):.1f} fps, "
          f"worst p95 {max(r[2] for r in morphs):.1f} ms")
    island.set_enabled(False)
    wisp.quit()


if __name__ == "__main__":
    main()
