"""Apps tab: search and launch installed apps (no API key needed)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from wisp.system.app_index import score
from wisp.ui.island.common import APPS, glyph_icon
from wisp.winapi.shell_icons import icon_png, parsing_name

ICON = 40


class AppsTab(QWidget):
    _icon_ready = Signal(int, bytes)

    def __init__(self, app_index, background, palette):
        super().__init__()
        self.index = app_index
        self.bg = background
        self.fallback = glyph_icon(APPS, palette.muted, ICON)
        self._icons: dict[int, QIcon] = {}
        self._requested: set[int] = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search apps")
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.search.returnPressed.connect(self._launch_first)
        layout.addWidget(self.search)
        self.grid = QListWidget()
        self.grid.setObjectName("Flat")
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setIconSize(QSize(ICON, ICON))
        self.grid.setGridSize(QSize(96, 86))
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setWordWrap(True)
        self.grid.itemActivated.connect(self._launch)
        self.grid.itemClicked.connect(self._launch)
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._menu)
        layout.addWidget(self.grid, 1)
        self.status = QLabel()
        self.status.setObjectName("Hint")
        layout.addWidget(self.status)
        self._icon_ready.connect(self._set_icon)

    def refresh(self) -> None:
        query = self.search.text().strip()
        entries = self.index.all()
        if query:
            ranked = sorted(((score(query, e.name, e.launch_count), e) for e in entries),
                            key=lambda pair: pair[0], reverse=True)
            entries = [e for s, e in ranked if s >= 60][:60]
        else:
            entries = entries[:60]
        self.grid.clear()
        for entry in entries:
            item = QListWidgetItem(self._icons.get(entry.id, self.fallback), entry.name)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(entry.name + ("  (pinned)" if entry.pinned else ""))
            self.grid.addItem(item)
            self._request_icon(entry)
        self.status.setText("" if entries else "No apps found. The list refreshes at start-up.")

    def _request_icon(self, entry) -> None:
        if entry.id in self._requested:
            return
        self._requested.add(entry.id)
        name = parsing_name(entry.target, entry.kind)
        self.bg.run(lambda: icon_png(name, ICON),
                    lambda png: self._icon_ready.emit(entry.id, png) if png else None)

    def _set_icon(self, entry_id: int, png: bytes) -> None:
        image = QImage.fromData(png, "PNG")
        if image.isNull():
            return
        icon = QIcon(QPixmap.fromImage(image))
        self._icons[entry_id] = icon
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            if item.data(Qt.ItemDataRole.UserRole).id == entry_id:
                item.setIcon(icon)

    def _launch(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole)
        self.status.setText(f"Opening {entry.name}…")
        self.bg.run(lambda: self.index.launch(entry), lambda _r: self.status.setText(""),
                    lambda exc: self.status.setText(f"Couldn't open {entry.name}: {exc}"))

    def _launch_first(self) -> None:
        if self.grid.count():
            self._launch(self.grid.item(0))

    def _menu(self, position) -> None:
        item = self.grid.itemAt(position)
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        action = menu.addAction("Unpin" if entry.pinned else "Pin to top")
        if menu.exec(self.grid.mapToGlobal(position)) == action:
            self.index.set_pinned(entry.id, not entry.pinned)
            self.refresh()
