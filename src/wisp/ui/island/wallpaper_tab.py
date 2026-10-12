"""Wallpaper tab: pick from Pictures and Windows wallpapers, or browse for an image."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wisp.system import wallpaper

THUMB = QSize(132, 80)


def load_thumbnail(path: str) -> QImage:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        reader.setScaledSize(size.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
    return reader.read()


class WallpaperTab(QWidget):
    _thumb = Signal(str, QImage)

    def __init__(self, background):
        super().__init__()
        self.bg = background
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.current = QLabel()
        self.current.setObjectName("Hint")
        browse = QPushButton("Choose image…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.current, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        self.grid = QListWidget()
        self.grid.setObjectName("Flat")
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setIconSize(THUMB)
        self.grid.setGridSize(QSize(THUMB.width() + 12, THUMB.height() + 12))
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.itemClicked.connect(lambda item: self._apply(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.grid, 1)
        self.status = QLabel()
        self.status.setObjectName("Hint")
        layout.addWidget(self.status)
        self._thumb.connect(self._add_thumb)

    def refresh(self) -> None:
        self.current.setText(f"Current: {Path(wallpaper.current()).name or 'solid colour'}")
        if self._loaded:
            return
        self._loaded = True

        def find() -> list[str]:
            paths = [str(p) for p in wallpaper.list_images()]
            for path in paths:
                image = load_thumbnail(path)  # QImage is safe off the UI thread
                if not image.isNull():
                    self._thumb.emit(path, image)
            return paths

        self.bg.run(find, lambda paths: self.status.setText(
            "" if paths else "No images found in Pictures or Windows wallpapers."))

    def _add_thumb(self, path: str, image: QImage) -> None:
        item = QListWidgetItem(QIcon(QPixmap.fromImage(image)), "")
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(Path(path).name)
        self.grid.addItem(item)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose wallpaper", str(Path.home() / "Pictures"),
            "Images (*.jpg *.jpeg *.png *.bmp)")
        if path:
            self._apply(path)

    def _apply(self, path: str) -> None:
        def done(_result) -> None:
            self.status.setText("Wallpaper changed.")
            self.current.setText(f"Current: {Path(path).name}")

        self.bg.run(lambda: wallpaper.set_wallpaper(path), done,
                    lambda exc: self.status.setText(str(exc)))
