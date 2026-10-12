"""Dev helper: render Wisp windows offscreen to PNG files for visual review.

Run: .venv\\Scripts\\python spikes\\render_ui.py [name ...]
Images go to spikes/out/. Uses a temporary data folder so real settings are untouched.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("WISP_DATA_DIR", tempfile.mkdtemp(prefix="wisp-render-"))

from PySide6.QtWidgets import QApplication

OUT = Path(__file__).parent / "out"


def render_settings(app: QApplication) -> None:
    from wisp import paths
    from wisp.app import WispApp

    wisp_app = WispApp(app, background=True)
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


RENDERERS = {"settings": render_settings, "console": render_console}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = QApplication(sys.argv[:1])
    names = sys.argv[1:] or list(RENDERERS)
    for name in names:
        RENDERERS[name](app)
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
