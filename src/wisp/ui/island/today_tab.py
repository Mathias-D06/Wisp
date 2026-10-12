"""Today tab: to-dos (add, complete, delete) and upcoming scheduled tasks."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wisp.ui.island.common import ADD, CALENDAR, GlyphButton, section


def due_text(due: datetime | None, now: datetime) -> str:
    if due is None:
        return ""
    if due.date() == now.date():
        return f"today {due.strftime('%H:%M')}"
    if due.date() == (now + timedelta(days=1)).date():
        return f"tomorrow {due.strftime('%H:%M')}"
    return due.strftime("%a %d %b %H:%M")


class TodayTab(QWidget):
    _changed = Signal()

    def __init__(self, todos, scheduler):
        super().__init__()
        self.todos = todos
        self.scheduler = scheduler
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(section("To-do"))
        row = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Add a to-do…")
        self.entry.returnPressed.connect(self._add)
        self.due_toggle = GlyphButton(CALENDAR, "Add a due time")
        self.due_toggle.setCheckable(True)
        self.due = QDateTimeEdit()
        self.due.setDisplayFormat("ddd d MMM HH:mm")
        self.due.setCalendarPopup(True)
        self.due.setVisible(False)
        self.due_toggle.toggled.connect(self._toggle_due)
        add = GlyphButton(ADD, "Add")
        add.clicked.connect(self._add)
        row.addWidget(self.entry, 1)
        row.addWidget(self.due_toggle)
        row.addWidget(add)
        layout.addLayout(row)
        layout.addWidget(self.due)
        self.list = QListWidget()
        self.list.setObjectName("Flat")
        self.list.itemChanged.connect(self._item_changed)
        layout.addWidget(self.list, 2)
        self.delete = QPushButton("Delete selected")
        self.delete.setProperty("danger", True)
        self.delete.clicked.connect(self._delete)
        layout.addWidget(self.delete, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(section("Coming up"))
        self.upcoming = QListWidget()
        self.upcoming.setObjectName("Flat")
        self.upcoming.setMaximumHeight(96)
        layout.addWidget(self.upcoming, 1)
        self._changed.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        todos.subscribe(self._changed.emit)
        scheduler.store.subscribe(self._changed.emit)

    def _toggle_due(self, on: bool) -> None:
        self.due.setVisible(on)
        if on:
            soon = datetime.now() + timedelta(hours=1)
            self.due.setDateTime(QDateTime(soon.year, soon.month, soon.day, soon.hour, 0, 0))

    def _add(self) -> None:
        text = self.entry.text().strip()
        if not text:
            return
        due = None
        if self.due_toggle.isChecked():
            due = self.due.dateTime().toPython().astimezone()
        self.todos.add(text, due)
        self.entry.clear()
        self.due_toggle.setChecked(False)

    def refresh(self) -> None:
        now = datetime.now().astimezone()
        self.list.blockSignals(True)
        self.list.clear()
        for todo in self.todos.list():
            when = due_text(todo.due_at, now)
            item = QListWidgetItem(f"{todo.text}" + (f"   · {when}" if when else ""))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, todo.id)
            if todo.due_at and todo.due_at < now:
                item.setToolTip("Overdue")
            self.list.addItem(item)
        if self.list.count() == 0:
            empty = QListWidgetItem("Nothing to do. Add one above or say “add a to-do…”.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
        self.list.blockSignals(False)
        self.upcoming.clear()
        for task, when in self.scheduler.upcoming(5):
            self.upcoming.addItem(f"{when.strftime('%a %H:%M')}  {task.title}")
        if self.upcoming.count() == 0:
            self.upcoming.addItem("No scheduled routines.")

    def _item_changed(self, item: QListWidgetItem) -> None:
        todo_id = item.data(Qt.ItemDataRole.UserRole)
        if todo_id is not None and item.checkState() == Qt.CheckState.Checked:
            self.todos.set_done(todo_id, True)

    def _delete(self) -> None:
        item = self.list.currentItem()
        todo_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if todo_id is None:
            return
        answer = QMessageBox.question(self, "Delete to-do", f"Delete “{item.text()}”?")
        if answer == QMessageBox.StandardButton.Yes:
            self.todos.delete(todo_id)
