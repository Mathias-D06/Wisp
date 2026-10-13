"""Feeds clipboard history from QClipboard.dataChanged, honouring exclusion markers.

Content marked with ExcludeClipboardContentFromMonitorProcessing or
CanIncludeInClipboardHistory=0 (password managers, Wisp's own dictation pastes) is skipped
(learn.microsoft.com dataxchg/clipboard-formats). Runs on the Qt thread.
"""

from __future__ import annotations

import contextlib
import logging

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer
from PySide6.QtGui import QGuiApplication, QImage

from wisp.stores.clipboard_history import ClipboardHistory
from wisp.system import clipboard

log = logging.getLogger(__name__)


def image_to_png(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data.data())


class ClipboardMonitor(QObject):
    def __init__(self, history: ClipboardHistory, owner_hwnd: int):
        super().__init__()
        self.history = history
        self.owner_hwnd = owner_hwnd
        self.skipped_excluded = 0
        self._pending = QTimer(self)
        self._pending.setSingleShot(True)
        self._pending.timeout.connect(self.capture)
        # A bound method (not a lambda) so the connection ends with this object or close().
        QGuiApplication.clipboard().dataChanged.connect(self._changed)
        self._closed = False

    def _changed(self) -> None:
        if not self._closed:
            self._pending.start(80)

    def close(self) -> None:
        """Stop watching (app quit, before the database closes)."""
        if self._closed:
            return
        self._closed = True
        self._pending.stop()
        with contextlib.suppress(RuntimeError, TypeError):  # already disconnected
            QGuiApplication.clipboard().dataChanged.disconnect(self._changed)

    def capture(self) -> None:
        """Read the clipboard once it settles (apps often write several formats in a row)."""
        if self._closed:
            return
        try:
            content = clipboard.read_for_history(self.owner_hwnd)
        except clipboard.ClipboardBusy:
            self._pending.start(200)
            return
        except Exception as exc:
            log.debug("Clipboard read failed: %s", exc)
            return
        if content.excluded:
            self.skipped_excluded += 1
            return
        try:
            if content.png:
                self.history.add_image(content.png)
            elif content.dib:
                image = QGuiApplication.clipboard().image()
                if not image.isNull():
                    self.history.add_image(image_to_png(image))
            elif content.text:
                self.history.add_text(content.text)
        except Exception:  # a slot must never raise into Qt's event loop
            log.exception("Saving a clipboard item failed")

    def recopy(self, item_id: int) -> bool:
        item = self.history.get(item_id)
        if item is None:
            return False
        board = QGuiApplication.clipboard()
        if item.kind == "image" and item.image:
            board.setImage(QImage.fromData(item.image, "PNG"))
        elif item.text is not None:
            board.setText(item.text)
        return True
