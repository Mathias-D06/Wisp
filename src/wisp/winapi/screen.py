"""Screen capture with mss, downscaled to keep image tokens low.

Coordinates are physical pixels: Qt makes the process Per-Monitor-V2 DPI aware
(doc.qt.io/qt-6/highdpi.html) and mss also requests per-monitor awareness (mss/windows/gdi.py).
"""

from __future__ import annotations

import ctypes
import io
from ctypes import wintypes
from dataclasses import dataclass

from PIL import Image

MAX_EDGE = 1280
JPEG_QUALITY = 72

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]


@dataclass
class Capture:
    jpeg: bytes
    width: int
    height: int
    region: tuple[int, int, int, int]  # left, top, right, bottom (physical px)
    image_size: tuple[int, int] = (0, 0)  # size of the JPEG the model sees

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        """Map a point in the sent image to physical screen pixels."""
        image_w, image_h = self.image_size if self.image_size[0] else (self.width, self.height)
        if not (0 <= x <= image_w and 0 <= y <= image_h):
            raise ValueError(f"({x:g}, {y:g}) is outside the {image_w}x{image_h} screenshot.")
        left, top, right, bottom = self.region
        sx = left + round(x * (right - left) / image_w)
        sy = top + round(y * (bottom - top) / image_h)
        return min(sx, right - 1), min(sy, bottom - 1)


def encode(image: Image.Image, max_edge: int = MAX_EDGE, quality: int = JPEG_QUALITY) -> bytes:
    image = image.convert("RGB")
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def grab(region: tuple[int, int, int, int]) -> Image.Image:
    from mss import MSS

    left, top, right, bottom = region
    with MSS() as sct:
        shot = sct.grab({"left": left, "top": top, "width": right - left,
                         "height": bottom - top})
        return Image.frombytes("RGB", shot.size, shot.rgb)


def monitors() -> list[tuple[int, int, int, int]]:
    from mss import MSS

    with MSS() as sct:
        return [(m["left"], m["top"], m["left"] + m["width"], m["top"] + m["height"])
                for m in sct.monitors[1:]]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                      ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)


def monitors_by_device() -> dict[str, tuple[int, int, int, int]]:
    """Each monitor's device name (the "DISPLAY1" kind) and its rectangle in physical
    pixels (EnumDisplayMonitors + GetMonitorInfoW with MONITORINFOEXW)."""
    found: dict[str, tuple[int, int, int, int]] = {}

    def collect(handle, _hdc, _rect, _data) -> bool:
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if _user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.rcMonitor
            found[info.szDevice] = (r.left, r.top, r.right, r.bottom)
        return True

    _user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(collect), 0)
    return found


def cursor_position() -> tuple[int, int]:
    point = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def monitor_at(x: int, y: int) -> tuple[int, int, int, int]:
    screens = monitors()
    for left, top, right, bottom in screens:
        if left <= x < right and top <= y < bottom:
            return left, top, right, bottom
    return screens[0]


def clamp_to_screens(region: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = region
    screens = monitors()
    v_left = min(s[0] for s in screens)
    v_top = min(s[1] for s in screens)
    v_right = max(s[2] for s in screens)
    v_bottom = max(s[3] for s in screens)
    clamped = (max(left, v_left), max(top, v_top), min(right, v_right), min(bottom, v_bottom))
    if clamped[2] - clamped[0] < 8 or clamped[3] - clamped[1] < 8:
        return None
    return clamped


def capture(region: tuple[int, int, int, int], max_edge: int = MAX_EDGE,
            hidden: list[tuple[int, int, int, int]] | None = None) -> Capture:
    """Grab ``region``, paint over ``hidden`` rectangles (blocklisted windows, D-052), encode."""
    image = grab(region)
    if hidden:
        from wisp.assist.privacy import mask

        image, _painted = mask(image, region, hidden)
    jpeg = encode(image, max_edge)
    width, height = image.size
    with Image.open(io.BytesIO(jpeg)) as sent:
        image_size = sent.size
    return Capture(jpeg, width, height, region, image_size)
