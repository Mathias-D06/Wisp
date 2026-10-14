"""Files & Share tab (D-051), in place of the Apps tab.

* One search box for apps and files (apps first; files from the Windows Search index, ranked
  fuzzily). Enter opens the first result. Voice "open X" is unchanged (the apps tools).
* The shelf: files dropped on the island (or on the strip) stay parked here, with thumbnails,
  until dragged out again into Explorer, an email, a chat…
* Recent files and the newest downloads.
* Quick actions on every file (right-click): open, show in Explorer, copy, copy path, rename,
  move, share (the Windows share sheet: Nearby Sharing and other apps), send to phone, shelf, and
  move to the Recycle Bin after a confirmation (never a permanent delete).
* The phone link: a QR code to open on the phone, the time left, Stop, and Accept/Decline for
  every file the phone wants to send.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wisp.files import actions
from wisp.files.finder import FileResult
from wisp.phone import qr
from wisp.phone.server import human_size
from wisp.system.app_index import score as app_score
from wisp.ui import theme
from wisp.ui.island.common import GlyphButton, glyph_icon, section
from wisp.ui.island.content import countdown_text
from wisp.winapi.shell_icons import icon_png, parsing_name

ROW_ICON = 24
SHELF_ICON = 48
LIST_ROWS = 40
QR_SIZE = 132
KIND = Qt.ItemDataRole.UserRole  # "file" | "app" | "header"
DATA = Qt.ItemDataRole.UserRole + 1  # Path or AppEntry


def when_text(modified: float, now: float) -> str:
    from datetime import datetime

    then = datetime.fromtimestamp(modified)
    today = datetime.fromtimestamp(now).date()
    if then.date() == today:
        return then.strftime("%H:%M")
    if (today - then.date()).days < 7:
        return then.strftime("%a %H:%M")
    return then.strftime("%d %b %Y")


class FileList(QListWidget):
    """Files you can drag out (as file URLs, so Explorer and other apps take them as files);
    with ``accept_drops`` files can be dropped in too (the shelf)."""

    dropped = Signal(list)

    def __init__(self, shelf_mode: bool = False, accept_drops: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("Flat")
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._accepts = accept_drops
        self.setAcceptDrops(accept_drops)
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop if accept_drops
                             else QListWidget.DragDropMode.DragOnly)
        if shelf_mode:
            self.setViewMode(QListWidget.ViewMode.IconMode)
            self.setFlow(QListWidget.Flow.LeftToRight)
            self.setWrapping(False)
            self.setIconSize(QSize(SHELF_ICON, SHELF_ICON))
            self.setGridSize(QSize(92, 84))
            self.setMovement(QListWidget.Movement.Static)
            self.setWordWrap(True)
            self.setFixedHeight(96)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            self.setIconSize(QSize(ROW_ICON, ROW_ICON))
            self.setProperty("dense", True)  # compact rows (island_stylesheet)
            self.setUniformItemSizes(True)

    def paths(self, items=None) -> list[Path]:
        chosen = items if items is not None else self.selectedItems()
        return [item.data(DATA) for item in chosen if item.data(KIND) == "file"]

    def mimeTypes(self) -> list[str]:
        return ["text/uri-list"]

    def mimeData(self, items) -> QMimeData:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in self.paths(items)])
        return mime

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.CopyAction

    @staticmethod
    def _local(mime) -> list[Path]:
        return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event) -> None:
        if self._accepts and event.source() is not self and self._local(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        paths = self._local(event.mimeData()) if self._accepts else []
        if paths and event.source() is not self:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.dropped.emit(paths)
        else:
            event.ignore()


class FilesTab(QWidget):
    _icon_ready = Signal(str, int, bytes)  # path key, size, png

    def __init__(self, finder, shelf, app_index, phone, background, palette, share=None,
                 confirm=None, clock=None):
        super().__init__()
        import time

        self.finder = finder
        self.shelf = shelf
        self.apps = app_index
        self.phone = phone
        self.bg = background
        self.palette = palette
        self.share = share  # callable(list[Path]) → opens the Windows share sheet
        self.confirm = confirm or self._ask
        self.clock = clock or time.time
        self._icons: dict[tuple[str, int], QIcon] = {}
        self._requested: set[tuple[str, int]] = set()
        self._search_id = 0
        self._file_icon = glyph_icon("file", palette.muted)
        self._app_icon = glyph_icon("apps", palette.muted)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(theme.SPACE["s"])
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search apps and files")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._query_changed)
        self.search.returnPressed.connect(self._open_first)
        self.phone_button = GlyphButton("phone", "Phone link: send files to and from your phone")
        self.phone_button.setCheckable(True)
        self.phone_button.clicked.connect(self._toggle_phone)
        top.addWidget(self.search, 1)
        top.addWidget(self.phone_button)
        layout.addLayout(top)

        self.phone_card = self._build_phone_card()
        layout.addWidget(self.phone_card)

        self.stack = QStackedWidget()
        browse = QWidget()
        browse_layout = QVBoxLayout(browse)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.setSpacing(theme.SPACE["xs"])
        shelf_head = QHBoxLayout()
        shelf_head.addWidget(section("Shelf"))
        self.shelf_hint = QLabel("Drop files on the island to park them here.")
        self.shelf_hint.setObjectName("Hint")
        shelf_head.addWidget(self.shelf_hint, 1)
        browse_layout.addLayout(shelf_head)
        self.shelf_list = FileList(shelf_mode=True, accept_drops=True)
        self.shelf_list.dropped.connect(self.add_to_shelf)
        browse_layout.addWidget(self.shelf_list)
        switch = QHBoxLayout()
        self.lists = QButtonGroup(self)
        for index, name in enumerate(("Recent", "Downloads")):
            button = QPushButton(name)
            button.setObjectName("Tab")
            button.setCheckable(True)
            self.lists.addButton(button, index)
            switch.addWidget(button)
        self.lists.button(0).setChecked(True)
        self.lists.idClicked.connect(lambda _i: self._fill_places())
        switch.addStretch(1)
        browse_layout.addLayout(switch)
        self.places = FileList()
        browse_layout.addWidget(self.places, 1)
        self.stack.addWidget(browse)
        self.results = FileList()
        self.stack.addWidget(self.results)
        layout.addWidget(self.stack, 1)
        self.status = QLabel()
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        for widget in (self.shelf_list, self.places, self.results):
            widget.itemActivated.connect(self._activate)
            widget.customContextMenuRequested.connect(
                lambda position, w=widget: self._menu(w, position))
        self._waiting_ids: list[int] = []
        self._recent: list[FileResult] = []
        self._downloads: list[FileResult] = []
        self._debounce = QTimer(self, singleShot=True, interval=180)
        self._debounce.timeout.connect(self._run_search)
        self._icon_ready.connect(self._set_icon)
        shelf.subscribe(self._fill_shelf)
        phone.changed.connect(self._update_phone)
        self._update_phone()

    # ----- building ----------------------------------------------------------------------------
    def _build_phone_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        outer = QVBoxLayout(card)
        row = QHBoxLayout()
        self.qr_label = QLabel()
        self.qr_label.setFixedSize(QR_SIZE, QR_SIZE)
        row.addWidget(self.qr_label)
        text = QVBoxLayout()
        self.phone_title = QLabel()
        self.phone_title.setObjectName("CardTitle")
        self.phone_title.setWordWrap(True)
        self.phone_text = QLabel()
        self.phone_text.setObjectName("Hint")
        self.phone_text.setWordWrap(True)
        self.phone_url = QLabel()
        self.phone_url.setObjectName("Hint")
        self.phone_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.phone_time = QLabel()
        buttons = QHBoxLayout()
        self.phone_stop = QPushButton("Stop")
        self.phone_stop.clicked.connect(self._stop_phone)
        self.phone_retry = QPushButton("Try again")
        self.phone_retry.clicked.connect(lambda: self.phone.start())
        buttons.addWidget(self.phone_stop)
        buttons.addWidget(self.phone_retry)
        buttons.addStretch(1)
        for widget in (self.phone_title, self.phone_text, self.phone_url, self.phone_time):
            text.addWidget(widget)
        text.addLayout(buttons)
        text.addStretch(1)
        row.addLayout(text, 1)
        outer.addLayout(row)
        self.waiting_box = QVBoxLayout()
        outer.addLayout(self.waiting_box)
        card.setVisible(False)
        return card

    # ----- data --------------------------------------------------------------------------------
    def refresh(self) -> None:
        """The tab came into view: reload the shelf, recent files and downloads."""
        self._fill_shelf()
        self.bg.run(lambda: (self.finder.recent(LIST_ROWS), self.finder.downloads(LIST_ROWS)),
                    self._got_places, lambda exc: self._say(f"Couldn't list files: {exc}"))

    def _got_places(self, result) -> None:
        self._recent, self._downloads = result
        self._fill_places()

    def _fill_shelf(self) -> None:
        self.shelf_list.clear()
        items = self.shelf.items()
        for entry in items:
            item = self._file_item(entry.path, SHELF_ICON, thumbnail=True)
            item.setText(entry.name)
            if not entry.exists:
                item.setToolTip(f"{entry.path}\nNot there any more")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self.shelf_list.addItem(item)
        self.shelf_hint.setText("Drag files out to use them; right-click for more." if items
                                else "Drop files on the island to park them here.")

    def _fill_places(self) -> None:
        self.places.clear()
        files = self._recent if self.lists.checkedId() == 0 else self._downloads
        now = self.clock()
        for result in files:
            item = self._file_item(result.path, ROW_ICON)
            item.setText(f"{result.name}   ·   {when_text(result.modified, now)}")
            self.places.addItem(item)
        if not files:
            empty = QListWidgetItem("Nothing here yet.")
            empty.setData(KIND, "header")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.places.addItem(empty)

    def _file_item(self, path: Path, size: int, thumbnail: bool = False) -> QListWidgetItem:
        key = (str(path).lower(), size)
        item = QListWidgetItem(self._icons.get(key, self._file_icon), path.name)
        item.setData(KIND, "file")
        item.setData(DATA, path)
        item.setToolTip(str(path))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        if key not in self._requested:
            self._requested.add(key)
            self.bg.run(lambda: icon_png(str(path), size, thumbnail),
                        lambda png: self._icon_ready.emit(key[0], size, png) if png else None)
        return item

    def _set_icon(self, key: str, size: int, png: bytes) -> None:
        image = QImage.fromData(png, "PNG")
        if image.isNull():
            return
        icon = QIcon(QPixmap.fromImage(image))
        self._icons[(key, size)] = icon
        for widget in (self.shelf_list, self.places, self.results):
            for row in range(widget.count()):
                item = widget.item(row)
                if item.data(KIND) == "file" and str(item.data(DATA)).lower() == key:
                    item.setIcon(icon)

    # ----- search ------------------------------------------------------------------------------
    def _query_changed(self, text: str) -> None:
        if text.strip():
            self.stack.setCurrentIndex(1)
            self._debounce.start()
        else:
            self._debounce.stop()
            self.stack.setCurrentIndex(0)

    def _run_search(self) -> None:
        query = self.search.text().strip()
        self._search_id += 1
        ticket = self._search_id
        apps = []
        if self.apps is not None:
            ranked = sorted(((app_score(query, e.name, e.launch_count), e)
                             for e in self.apps.all()), key=lambda pair: pair[0], reverse=True)
            apps = [entry for value, entry in ranked if value >= 60][:4]
        self._show_results(query, apps, None)
        self.bg.run(lambda: self.finder.search(query, 25),
                    lambda files: self._show_results(query, apps, files)
                    if ticket == self._search_id else None,
                    lambda exc: self._say(f"Search failed: {exc}"))

    def _show_results(self, query: str, apps: list, files: list[FileResult] | None) -> None:
        self.results.clear()
        if apps:
            self._header(self.results, "Apps")
            for entry in apps:
                item = QListWidgetItem(self._app_icon, entry.name)
                item.setData(KIND, "app")
                item.setData(DATA, entry)
                self.results.addItem(item)
                self._request_app_icon(entry, item)
        if files is None:
            self._header(self.results, "Searching files…")
            return
        if files:
            self._header(self.results, "Files")
            now = self.clock()
            for result in files:
                item = self._file_item(result.path, ROW_ICON)
                item.setText(f"{result.name}   ·   {result.path.parent.name}   ·   "
                             f"{when_text(result.modified, now)}")
                self.results.addItem(item)
        elif not apps:
            self._header(self.results, f"Nothing called “{query}”.")
        if not self.finder.used_index:
            self._say("Windows Search isn't available, so only your main folders were searched.")

    @staticmethod
    def _header(widget: QListWidget, text: str) -> None:
        item = QListWidgetItem(text)
        item.setData(KIND, "header")
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        widget.addItem(item)

    def _request_app_icon(self, entry, item: QListWidgetItem) -> None:
        key = (f"app:{entry.id}", ROW_ICON)
        if key in self._icons:
            item.setIcon(self._icons[key])
            return
        name = parsing_name(entry.target, entry.kind)

        def done(png) -> None:
            if not png:
                return
            image = QImage.fromData(png, "PNG")
            if not image.isNull():
                self._icons[key] = QIcon(QPixmap.fromImage(image))
                for row in range(self.results.count()):
                    other = self.results.item(row)
                    if other.data(KIND) == "app" and other.data(DATA).id == entry.id:
                        other.setIcon(self._icons[key])

        self.bg.run(lambda: icon_png(name, ROW_ICON), done)

    def _open_first(self) -> None:
        for row in range(self.results.count()):
            item = self.results.item(row)
            if item.data(KIND) in ("app", "file"):
                self._activate(item)
                return

    # ----- actions -----------------------------------------------------------------------------
    def _say(self, text: str) -> None:
        self.status.setText(text)

    def _ask(self, question: str) -> bool:
        return QMessageBox.question(self, "Wisp", question) == QMessageBox.StandardButton.Yes

    def _activate(self, item: QListWidgetItem) -> None:
        kind = item.data(KIND)
        if kind == "app":
            entry = item.data(DATA)
            self._say(f"Opening {entry.name}…")
            self.bg.run(lambda: self.apps.launch(entry), lambda _r: self._say(""),
                        lambda exc: self._say(f"Couldn't open {entry.name}: {exc}"))
        elif kind == "file":
            self._do(actions.open_file, item.data(DATA))

    def _do(self, action, *args, done: str = "") -> object:
        try:
            result = action(*args)
        except actions.ActionError as exc:
            self._say(str(exc))
            return None
        self._say(done)
        return result

    def add_to_shelf(self, paths: list[Path]) -> None:
        added = self.shelf.add(paths)
        if added:
            self._say(f"Parked {len(added)} item{'s' if len(added) != 1 else ''} on the shelf.")

    def _menu(self, widget: FileList, position) -> None:
        item = widget.itemAt(position)
        if item is not None and item.data(KIND) == "app":
            self._app_menu(widget, item, position)
            return
        if item is None or item.data(KIND) != "file":
            return
        if not item.isSelected():
            widget.clearSelection()
            item.setSelected(True)
        paths = widget.paths()
        path = item.data(DATA)
        p = theme.palette_for(self)
        menu = QMenu(self)

        def add(icon: str, text: str, handler) -> None:
            menu.addAction(glyph_icon(icon, p.secondary), text).triggered.connect(handler)

        add("open", "Open", lambda: self._do(actions.open_file, path))
        add("folder", "Show in Explorer", lambda: self._do(actions.reveal, path))
        add("copy", "Copy", lambda: self._do(actions.copy_files, paths,
                                             done=f"Copied {len(paths)} to the clipboard."))
        add("clipboard", "Copy path", lambda: self._do(actions.copy_path, paths,
                                                       done="Path copied."))
        if len(paths) == 1:
            add("rename", "Rename…", lambda: self._rename(path))
        add("move", "Move to…", lambda: self._move(paths))
        menu.addSeparator()
        if self.share is not None:
            add("share", "Share…", lambda: self._share(paths))
        add("phone", "Send to phone", lambda: self.send_to_phone(paths))
        if widget is self.shelf_list:
            add("close", "Remove from shelf", lambda: [self.shelf.remove(x) for x in paths])
        else:
            add("pin", "Add to shelf", lambda: self.add_to_shelf(paths))
        menu.addSeparator()
        add("delete", "Move to Recycle Bin…", lambda: self._recycle(paths))
        menu.exec(widget.viewport().mapToGlobal(position))

    def _app_menu(self, widget: FileList, item: QListWidgetItem, position) -> None:
        entry = item.data(DATA)
        menu = QMenu(self)
        open_action = menu.addAction("Open")
        pin = menu.addAction("Unpin" if entry.pinned else "Pin to top")
        chosen = menu.exec(widget.viewport().mapToGlobal(position))
        if chosen == open_action:
            self._activate(item)
        elif chosen == pin:
            self.apps.set_pinned(entry.id, not entry.pinned)
            self._run_search()

    def _rename(self, path: Path) -> None:
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=path.name)
        if ok and name and name != path.name:
            renamed = self._do(actions.rename, path, name, self.shelf.renamed)
            if renamed is not None:
                self._say(f"Renamed to {renamed.name}.")
                self.refresh()

    def _move(self, paths: list[Path]) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Move to", str(paths[0].parent))
        if not folder:
            return
        moved = [self._do(actions.move, path, Path(folder), self.shelf.renamed) for path in paths]
        done = [m for m in moved if m is not None]
        if done:
            self._say(f"Moved {len(done)} to {Path(folder).name}.")
            self.refresh()

    def _share(self, paths: list[Path]) -> None:
        try:
            self.share(paths)
        except OSError as exc:
            self._say(f"Windows couldn't open the share sheet ({exc}).")

    def _recycle(self, paths: list[Path]) -> None:
        names = paths[0].name if len(paths) == 1 else f"{len(paths)} items"
        if not self.confirm(f"Move {names} to the Recycle Bin? You can restore "
                            f"{'it' if len(paths) == 1 else 'them'} from there."):
            return

        def work() -> list[str]:
            problems = []
            for path in paths:
                try:
                    actions.recycle(path)
                except actions.ActionError as exc:
                    problems.append(str(exc))
            return problems

        def done(problems: list[str]) -> None:
            self._say(problems[0] if problems else f"Moved {names} to the Recycle Bin.")
            self.shelf.forget_missing()
            self.refresh()

        self.bg.run(work, done, lambda exc: self._say(str(exc)))

    # ----- phone link --------------------------------------------------------------------------
    def send_to_phone(self, paths: list[Path]) -> None:
        self.phone.start(paths)

    def _toggle_phone(self) -> None:
        if self.phone.running:
            self.phone.stop()
        else:
            self.phone.start()

    def _stop_phone(self) -> None:
        if self.phone.running:
            self.phone.stop()
        else:
            self.phone.error = ""
            self._update_phone()

    def _update_phone(self) -> None:
        phone = self.phone
        running = phone.running
        self.phone_card.setVisible(running or bool(phone.error))
        self.phone_button.setChecked(running)
        self.qr_label.setVisible(running)
        self.phone_url.setVisible(running)
        self.phone_time.setVisible(running)
        self.phone_retry.setVisible(not running)
        self.phone_stop.setText("Stop" if running else "Close")
        if running:
            if self.qr_label.property("url") != phone.url:
                self.qr_label.setPixmap(QPixmap.fromImage(qr.image(phone.url, QR_SIZE)))
                self.qr_label.setProperty("url", phone.url)
            offered = phone.offers()
            self.phone_title.setText("Scan with your phone's camera")
            self.phone_text.setText(
                f"Phone and PC on the same Wi-Fi (“{phone.network}”). "
                + (f"Ready to download: {', '.join(p.name for p in offered[:3])}"
                   f"{' …' if len(offered) > 3 else ''}. " if offered else "")
                + "Files from the phone need your OK here.")
            self.phone_url.setText(phone.url)
            now = self.clock()
            self.phone_time.setText(f"Stops in {countdown_text(now + phone.remaining_s(), now)}")
        else:
            self.phone_title.setText("Phone link isn't available")
            self.phone_text.setText(phone.error)
        self._fill_waiting()

    def _fill_waiting(self) -> None:
        ids = [upload.id for upload in self.phone.waiting]
        if ids == self._waiting_ids:
            return  # unchanged: keep the buttons (the service updates every second)
        self._waiting_ids = ids
        while self.waiting_box.count():
            item = self.waiting_box.takeAt(0)
            if item.layout() is not None:
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget() is not None:
                        child.widget().hide()
                        child.widget().deleteLater()
            elif item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        for upload in list(self.phone.waiting):
            row = QHBoxLayout()
            label = QLabel(f"Your phone wants to send <b>{_escape(upload.name)}</b> "
                           f"({human_size(upload.size)})")
            label.setWordWrap(True)
            accept = QPushButton("Accept")
            accept.setProperty("primary", True)
            accept.clicked.connect(lambda _c=False, u=upload: self.phone.accept(u))
            decline = QPushButton("Decline")
            decline.clicked.connect(lambda _c=False, u=upload: self.phone.decline(u))
            row.addWidget(label, 1)
            row.addWidget(accept)
            row.addWidget(decline)
            self.waiting_box.addLayout(row)


def _escape(text: str) -> str:
    import html

    return html.escape(text)
