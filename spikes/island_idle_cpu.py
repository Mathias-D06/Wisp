"""Idle CPU of Wisp with the island visible (D-047).

spikes/idle_cpu.py measures a separate `python -m wisp --background`, but the island hides
itself whenever a full-screen app is in front, so that run can end up measuring a hidden island.
This one builds WispApp in-process (throwaway data folder, no key), keeps the island visible by
not polling for full-screen apps, waits 30 s for start-up work to finish, then measures this
process's CPU time (time.process_time) with Reduce motion, then with motion on. Nothing is read
from the screen.
Run: .venv\\Scripts\\python spikes\\island_idle_cpu.py [seconds]
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("WISP_DATA_DIR", tempfile.mkdtemp(prefix="wisp-idle-island-"))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def cpu_seconds() -> float:
    """This process's user + system CPU time (time.process_time)."""
    return time.process_time()


def main() -> None:
    from wisp.app import WispApp
    from wisp.ui import motion

    window = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    app = QApplication(sys.argv[:1])
    wisp = WispApp(app, background=True)
    wisp.start()
    island = wisp.island
    if hasattr(island, "machine"):  # this works against older Wisp code too (before/after)
        island._poll.stop()  # stay visible even if a full-screen app is in front
        island.machine.set_hidden(False)

    def pump(seconds: float) -> None:
        """Wait in a real event loop (a polling loop would itself cost CPU)."""
        loop = QEventLoop()
        QTimer.singleShot(int(seconds * 1000), loop.quit)
        loop.exec()

    def measure(label: str, seconds: float) -> None:
        pump(5)
        start_cpu, start = cpu_seconds(), time.monotonic()
        pump(seconds)
        used, elapsed = cpu_seconds() - start_cpu, time.monotonic() - start
        print(f"{label}: island visible={island.isVisible()} — {used:.2f} s CPU over "
              f"{elapsed:.0f} s = {100 * used / elapsed:.2f} % of one core")

    pump(30)  # start-up work (the app index scan, the scheduler) finishes first
    motion.configure(reduce_motion=True)
    island.update()
    measure("idle, Reduce motion", window / 2)
    motion.configure(reduce_motion=False)
    if hasattr(island, "_wake"):
        island._wake()
    measure("idle, motion on (orb glow)", window)
    wisp.quit()


if __name__ == "__main__":
    main()
