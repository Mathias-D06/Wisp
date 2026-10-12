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

from PySide6.QtWidgets import QApplication  # noqa: E402

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


RENDERERS = {"settings": render_settings}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = QApplication(sys.argv[:1])
    names = sys.argv[1:] or list(RENDERERS)
    for name in names:
        RENDERERS[name](app)
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
