"""Dev helper: capture the console and Settings as they really look on screen (Mica needs the
desktop behind the window, which an off-screen grab can't show). Only each window's own
rectangle is captured, and only when no other window covers it (a window opened behind another
app is skipped, so other apps' content is never saved). Uses a throwaway data folder.

Run: .venv\\Scripts\\python spikes\\capture_onscreen.py OUT_DIR
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("WISP_DATA_DIR", tempfile.mkdtemp(prefix="wisp-capture-"))
os.environ.pop("WISP_NO_MICA", None)

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def pump(app: QApplication, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def uncovered(hwnd: int, bounds: tuple[int, int, int, int]) -> bool:
    """True only if ``hwnd`` is the top-level window at every point of a 5×5 grid inside
    ``bounds``: a window that opened behind another app must not be grabbed, or the capture
    would hold that app's content instead of Wisp's."""
    from wisp.winapi import windows

    left, top, right, bottom = bounds
    for fx in (0.05, 0.27, 0.5, 0.73, 0.95):
        for fy in (0.05, 0.27, 0.5, 0.73, 0.95):
            x, y = int(left + fx * (right - left)), int(top + fy * (bottom - top))
            info = windows.window_at(x, y)
            if info is None or info.hwnd != hwnd:
                return False
    return True


def capture(window, path: Path) -> bool:
    from wisp.winapi import screen, windows

    hwnd = int(window.winId())
    bounds = windows.frame_bounds(hwnd)
    if bounds is None or not uncovered(hwnd, bounds):
        print(f"not saved: {path.name} — another window covers Wisp's; clear the desktop and retry")
        return False
    image = screen.grab(bounds).convert("RGBA")
    # Keep only the window's own rounded shape: the corners and the 1 px edge let whatever is
    # behind the window show through, and that is not Wisp's to save.
    from PIL import Image, ImageDraw

    radius = round(8 * window.devicePixelRatioF()) + 1  # DWMWCP_ROUND is 8 px at 100 %
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((1, 1, image.width - 2, image.height - 2), radius,
                                           fill=255)
    image.putalpha(mask)
    image.save(path)
    return True


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "spikes/out")
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    from wisp.app import WispApp

    wisp_app = WispApp(app, background=True)
    console = wisp_app.console
    console.add("user", "Open Spotify and play something chill", True, 1)
    console.add("model", "Opening Spotify now. Want me to search for a lofi playlist?", True)
    console.add("notice", "Microphone muted.", True)
    console.add("user", "yes and turn the volume", False, 2)
    console.resize(560, 600)
    console.move(120, 120)
    console.open()
    pump(app, 1.5)
    saved = [capture(console, out / "console_onscreen.png")]
    console.hide()
    wisp_app.open_settings("Loadout")
    dialog = wisp_app._settings_dialog
    dialog.move(140, 100)
    pump(app, 1.5)
    saved.append(capture(dialog, out / "settings_onscreen.png"))
    dialog.hide()
    wisp_app.quit()
    print(f"saved {sum(saved)} of 2 captures in {out}")


if __name__ == "__main__":
    main()
