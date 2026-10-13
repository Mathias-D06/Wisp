"""Render the Wisp orb (the same drawing as the tray icon) into packaging/wisp.ico for the exe,
shortcuts and the installer.

Run: .venv\\Scripts\\python packaging\\make_icon.py
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtWidgets import QApplication

from wisp.ui.icons import orb_pixmap

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
ACCENT = "#7c5cff"
OUT = Path(__file__).with_name("wisp.ico")


def main() -> None:
    app = QApplication.instance() or QApplication([])
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    orb_pixmap(256, ACCENT).toImage().save(buffer, "PNG")
    buffer.close()
    big = Image.open(io.BytesIO(bytes(data.data()))).convert("RGBA")
    # Small sizes are drawn natively (crisper than downscaling the 256 px image).
    frames = {}
    for size in SIZES:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        orb_pixmap(size, ACCENT).toImage().save(buffer, "PNG")
        buffer.close()
        frames[size] = Image.open(io.BytesIO(bytes(data.data()))).convert("RGBA")
    big.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES],
             append_images=[frames[s] for s in SIZES if s != 256])
    del app
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
