"""Settings → Action log: every tool call Wisp made or refused, newest first (F12.5)."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from wisp.ui.settings.base import SettingsPage, hint

SHOWN = 500


def is_problem(entry) -> bool:
    """Refused, cancelled, expired, invalid or failed (a pending confirmation is not)."""
    if entry.decision == "confirm-requested":
        return False
    return not (entry.ok and entry.decision.startswith("allow"))


def matches(entry, query: str, problems_only: bool) -> bool:
    if problems_only and not is_problem(entry):
        return False
    if not query:
        return True
    query = query.casefold()
    return any(query in field.casefold() for field in (entry.tool, entry.args, entry.result,
                                                        entry.decision, entry.origin))


class ActionLogPage(SettingsPage):
    title = "Action log"
    _changed = Signal()

    def __init__(self, action_log, log_folder: str | None = None):
        super().__init__()
        self.action_log = action_log
        self.log_folder = log_folder
        layout = QVBoxLayout(self)
        layout.addWidget(hint(
            "Every action Wisp took or was refused, with who asked (voice, routine or a click in "
            "Wisp), the safety decision and the result. API keys are removed before anything is "
            "stored. The newest 5000 entries are kept."))
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by tool, text or decision")
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.problems = QCheckBox("Only refused, cancelled or failed")
        self.problems.toggled.connect(lambda _c: self.refresh())
        top.addWidget(self.search, 1)
        top.addWidget(self.problems)
        layout.addLayout(top)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Time", "From", "Action", "Decision", "Result"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for column in range(4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.currentCellChanged.connect(lambda row, *_: self._show_details(row))
        layout.addWidget(self.table, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(110)
        self.details.setPlaceholderText("Select an entry to see its arguments and result.")
        layout.addWidget(self.details)
        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        clear = QPushButton("Clear log…")
        clear.setProperty("danger", True)
        clear.clicked.connect(self._clear)
        buttons.addWidget(refresh)
        buttons.addWidget(clear)
        if log_folder:
            folder = QPushButton("Open log folder")
            folder.clicked.connect(lambda: os.startfile(log_folder))
            buttons.addWidget(folder)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._entries: list = []
        self._changed.connect(self._refresh_if_visible, Qt.ConnectionType.QueuedConnection)
        action_log.subscribe(self._changed.emit)  # written from worker threads

    def _refresh_if_visible(self) -> None:
        if self.isVisible():
            self.refresh()

    def refresh(self) -> None:
        query = self.search.text().strip()
        entries = [e for e in self.action_log.recent(SHOWN)
                   if matches(e, query, self.problems.isChecked())]
        self._entries = entries
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            outcome = "✓" if entry.ok else "✗"
            values = [entry.ts[5:16].replace("T", " "), entry.origin, entry.tool, entry.decision,
                      f"{outcome} {entry.result[:120]}"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 4 and not entry.ok:
                    item.setForeground(Qt.GlobalColor.red)
                self.table.setItem(row, column, item)
        self.details.clear()

    def showEvent(self, event) -> None:
        self.refresh()
        super().showEvent(event)

    def _show_details(self, row: int) -> None:
        if 0 <= row < len(self._entries):
            entry = self._entries[row]
            self.details.setPlainText(
                f"{entry.ts}  {entry.origin}  {entry.tool}  ({entry.duration_ms} ms)\n"
                f"Decision: {entry.decision}\nArguments: {entry.args}\nResult: {entry.result}")

    def _clear(self) -> None:
        answer = QMessageBox.question(self, "Clear action log",
                                      "Delete the whole action log? This can't be undone.")
        if answer == QMessageBox.StandardButton.Yes:
            self.action_log.clear()
            self.refresh()
