"""App icons via the documented IShellItemImageFactory::GetImage (SIIGBF_ICONONLY), for both
Store apps (parsing name ``shell:AppsFolder\\<AUMID>``) and files. With ``thumbnail=True`` the
flag is left out (SIIGBF_RESIZETOFIT only), so the shell returns a file's thumbnail (a photo's
picture, a document's first page) where it has one and its icon otherwise.

The interface IID {bcc18b79-ba16-442f-80c4-8a59c30c463b} is registered on the system and
confirmed functionally by ``spikes/shell_icon_probe.py`` (QueryInterface succeeds and icons are
returned for a Store app and a desktop app). The caller frees the HBITMAP with
DeleteObject (per the docs). Extraction can be slow: call from worker threads, never the UI
thread.
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, Structure, byref, c_int, wintypes

from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

IID_IShellItemImageFactory = GUID("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")
SIIGBF_RESIZETOFIT = 0x0
SIIGBF_ICONONLY = 0x4


class SIZE(Structure):
    _fields_ = [("cx", c_int), ("cy", c_int)]


class IShellItemImageFactory(IUnknown):
    _iid_ = IID_IShellItemImageFactory
    _methods_ = [  # noqa: RUF012  (comtypes reads this class attribute to build the vtable)
        COMMETHOD([], HRESULT, "GetImage",
                  (["in"], SIZE, "size"),
                  (["in"], c_int, "flags"),
                  (["out"], POINTER(wintypes.HBITMAP), "phbm")),
    ]


_shell32 = ctypes.WinDLL("shell32")
_shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p,
                                                 ctypes.POINTER(GUID), ctypes.c_void_p]
_shell32.SHCreateItemFromParsingName.restype = HRESULT
_gdi32 = ctypes.WinDLL("gdi32")
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
_user32 = ctypes.WinDLL("user32")
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]


class BITMAPINFOHEADER(Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def _to_qimage(hbitmap, size: int):
    """Copy the 32-bpp bits with GetDIBits (top-down: negative height) keeping alpha;
    QImage.fromHBITMAP drops the alpha channel."""
    from PySide6.QtGui import QImage

    header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER))
    hdc = _user32.GetDC(None)
    try:
        if not _gdi32.GetDIBits(hdc, hbitmap, 0, 0, None, byref(header), 0):
            return None
        width, height = header.biWidth, abs(header.biHeight)
        header.biHeight, header.biBitCount, header.biCompression = -height, 32, 0
        buffer = (ctypes.c_ubyte * (width * height * 4))()
        if not _gdi32.GetDIBits(hdc, hbitmap, 0, height, buffer, byref(header), 0):
            return None
    finally:
        _user32.ReleaseDC(None, hdc)
    data = bytes(buffer)
    has_alpha = any(data[3::4])
    fmt = QImage.Format.Format_ARGB32_Premultiplied if has_alpha else QImage.Format.Format_RGB32
    return QImage(data, width, height, width * 4, fmt).copy()


def parsing_name(target: str, kind: str) -> str:
    return f"shell:AppsFolder\\{target}" if kind == "aumid" else target


def icon_png(name: str, size: int = 48, thumbnail: bool = False) -> bytes | None:
    """PNG bytes of the item's icon (or thumbnail), or None if the shell has none."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    factory = POINTER(IShellItemImageFactory)()
    try:
        _shell32.SHCreateItemFromParsingName(name, None, byref(IID_IShellItemImageFactory),
                                             byref(factory))
        flags = SIIGBF_RESIZETOFIT | (0 if thumbnail else SIIGBF_ICONONLY)
        hbitmap = factory.GetImage(SIZE(size, size), flags)
    except OSError:
        return None
    try:
        image = _to_qimage(hbitmap, size)
        if image is None or image.isNull():
            return None
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        return bytes(data.data())
    finally:
        _gdi32.DeleteObject(hbitmap)
