"""Settings → Memories: view, search, add, edit, pin and delete what Wisp remembers (F8.3)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from wisp.stores.memory import SESSION_FACTS
from wisp.ui.settings.base import SettingsPage, hint


class MemoriesPage(SettingsPage):
    title = "Memories"
    _changed = Signal()

    def __init__(self, memory):
        super().__init__()
        self.memory = memory
        layout = QVBoxLayout(self)
        layout.addWidget(hint(
            "Facts you asked Wisp to remember (“remember that my sister's birthday is 3 May”). "
            f"Each conversation starts with up to {SESSION_FACTS} of them — pinned first, then "
            "the ones Wisp looks up most; it searches the rest when needed. Double-click a fact "
            "to edit it. Everything stays on this PC."))
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search memories")
        self.search.textChanged.connect(lambda _t: self.refresh())
        top.addWidget(self.search, 1)
        layout.addLayout(top)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Pinned", "Fact", "Changed"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._item_changed)
        layout.addWidget(self.table, 1)
        add_row = QHBoxLayout()
        self.new_fact = QLineEdit()
        self.new_fact.setPlaceholderText("Add a fact, e.g. “I work from home on Fridays”")
        self.new_fact.returnPressed.connect(self._add)
        add = QPushButton("Add")
        add.clicked.connect(self._add)
        add_row.addWidget(self.new_fact, 1)
        add_row.addWidget(add)
        layout.addLayout(add_row)
        buttons = QHBoxLayout()
        delete = QPushButton("Delete selected")
        delete.setProperty("danger", True)
        delete.clicked.connect(self._delete_selected)
        clear = QPushButton("Delete all…")
        clear.setProperty("danger", True)
        clear.clicked.connect(self._clear)
        buttons.addWidget(delete)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.status = QLabel()
        self.status.setProperty("muted", True)
        layout.addWidget(self.status)
        self._ids: list[int] = []
        self._changed.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        memory.subscribe(self._changed.emit)  # tool calls write from worker threads

    def refresh(self) -> None:
        query = self.search.text().strip()
        memories = self.memory.search(query, 200) if query else self.memory.all()
        self._ids = [m.id for m in memories]
        self.table.blockSignals(True)
        self.table.setRowCount(len(memories))
        for row, memory in enumerate(memories):
            pin = QTableWidgetItem()
            pin.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                         | Qt.ItemFlag.ItemIsSelectable)
            pin.setCheckState(Qt.CheckState.Checked if memory.pinned else Qt.CheckState.Unchecked)
            fact = QTableWidgetItem(memory.text)
            changed = QTableWidgetItem(memory.updated_at[:16].replace("T", " "))
            changed.setFlags(changed.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, pin)
            self.table.setItem(row, 1, fact)
            self.table.setItem(row, 2, changed)
        self.table.blockSignals(False)
        total = self.memory.count()
        self.status.setText(f"{total} memor{'y' if total == 1 else 'ies'} stored.")

    def _item_changed(self, item: QTableWidgetItem) -> None:
        memory_id = self._ids[item.row()]
        try:
            if item.column() == 0:
                self.memory.update(memory_id, pinned=item.checkState() == Qt.CheckState.Checked)
            elif item.column() == 1:
                self.memory.update(memory_id, text=item.text())
        except (ValueError, KeyError) as exc:
            self.status.setText(f"Not saved: {exc}")
            self._changed.emit()

    def _add(self) -> None:
        text = self.new_fact.text().strip()
        if not text:
            return
        try:
            self.memory.add(text)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.new_fact.clear()

    def _selected_ids(self) -> list[int]:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        return [self._ids[row] for row in sorted(rows) if row < len(self._ids)]

    def _delete_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        answer = QMessageBox.question(self, "Delete memories",
                                      f"Delete {len(ids)} selected memor"
                                      f"{'y' if len(ids) == 1 else 'ies'}?")
        if answer == QMessageBox.StandardButton.Yes:
            for memory_id in ids:
                self.memory.delete(memory_id)

    def _clear(self) -> None:
        answer = QMessageBox.question(self, "Delete all memories",
                                      "Delete everything Wisp remembers? This can't be undone.")
        if answer == QMessageBox.StandardButton.Yes:
            self.memory.clear()
