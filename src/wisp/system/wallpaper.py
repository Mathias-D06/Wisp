"""Desktop wallpaper: current image, available images, set (documented SystemParametersInfoW
SPI_GETDESKWALLPAPER = 0x0073 / SPI_SETDESKWALLPAPER = 0x0014 with SPIF_UPDATEINIFILE |
SPIF_SENDWININICHANGE)."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

SPI_SETDESKWALLPAPER = 0x0014
SPI_GETDESKWALLPAPER = 0x0073
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDWININICHANGE = 0x02
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def current() -> str:
    buffer = ctypes.create_unicode_buffer(520)
    ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 520, buffer, 0)
    return buffer.value


def set_wallpaper(path: str) -> None:
    full = Path(path).resolve()
    if not full.is_file() or full.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("Choose a JPG, PNG or BMP image.")
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, str(full), SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE)
    if not ok:
        raise OSError(f"Windows refused the wallpaper (error {ctypes.GetLastError()}).")


def default_folders() -> list[Path]:
    folders = [Path.home() / "Pictures",
               Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "Web" / "Wallpaper"]
    return [f for f in folders if f.is_dir()]


def list_images(folders: list[Path] | None = None, limit: int = 120) -> list[Path]:
    images: list[Path] = []
    for folder in folders or default_folders():
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in sorted(files):
                if Path(name).suffix.lower() in IMAGE_SUFFIXES:
                    images.append(Path(root) / name)
                    if len(images) >= limit:
                        return images
    return images
