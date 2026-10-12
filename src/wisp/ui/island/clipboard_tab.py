"""Clipboard tab (F7.10): searchable history of text and images; click to copy again."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ClipboardTab(QWidget):
    _changed = Signal()

    def __init__(self, history, monitor):
        super().__init__()
        self.history = history
        self.monitor = monitor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search clipboard history")
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.clear = QPushButton("Clear all")
        self.clear.setProperty("danger", True)
        self.clear.clicked.connect(self._clear)
        row.addWidget(self.search, 1)
        row.addWidget(self.clear)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setObjectName("Flat")
        self.list.setIconSize(QSize(48, 48))
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(self._recopy)
        layout.addWidget(self.list, 1)
        self.status = QLabel("Click an item to copy it again. Password-manager items are never "
                             "stored.")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._changed.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        history.subscribe(self._changed.emit)

    def refresh(self) -> None:
        self.list.clear()
        for item in self.history.items(self.search.text().strip(), 100):
            entry = QListWidgetItem(item.preview if item.kind == "text" else "Image")
            entry.setData(Qt.ItemDataRole.UserRole, item.id)
            entry.setToolTip(item.created_at)
            if item.kind == "image" and item.image:
                image = QImage.fromData(item.image, "PNG")
                if not image.isNull():
                    entry.setIcon(QIcon(QPixmap.fromImage(image.scaled(
                        96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))))
            self.list.addItem(entry)
        if self.list.count() == 0:
            placeholder = QListWidgetItem("Nothing copied yet." if not self.search.text()
                                          else "No matches.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(placeholder)

    def _recopy(self, entry: QListWidgetItem) -> None:
        item_id = entry.data(Qt.ItemDataRole.UserRole)
        if item_id is not None and self.monitor.recopy(item_id):
            self.status.setText("Copied — paste with Ctrl+V.")
            QTimer.singleShot(2500, lambda: self.status.setText(
                "Click an item to copy it again. Password-manager items are never stored."))

    def _clear(self) -> None:
        answer = QMessageBox.question(self, "Clear clipboard history",
                                      "Remove everything from Wisp's clipboard history?")
        if answer == QMessageBox.StandardButton.Yes:
            self.history.clear()
