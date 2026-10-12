"""Settings → Routines: list, edit, run, switch off and delete scheduled tasks."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from wisp.scheduling.spec import DAYS, REPEATS, ScheduleError, parse_schedule
from wisp.ui.settings.base import SettingsPage, hint

REPEAT_LABELS = {"none": "Once", "daily": "Every day", "weekdays": "Weekdays",
                 "weekly": "Weekly", "monthly": "Monthly", "hourly": "Every hour"}


def _step_text(step: dict) -> str:
    if "prompt" in step:
        return f"Ask Wisp: {step['prompt']}"
    args = ", ".join(f"{k}={v!r}" for k, v in step.get("args", {}).items())
    return f"{step['tool']}({args})"


class TaskEditor(QDialog):
    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit routine")
        self.task = task
        self.result_schedule = None
        self.steps = list(task.steps)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(task.title)
        self.repeat = QComboBox()
        for key in REPEATS:
            self.repeat.addItem(REPEAT_LABELS[key], key)
        self.repeat.setCurrentIndex(REPEATS.index(task.schedule.repeat))
        self.when = QDateTimeEdit()
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("ddd d MMM yyyy HH:mm")
        at = (datetime.fromisoformat(task.schedule.at) if task.schedule.at
              else datetime.now().astimezone())
        self.when.setDateTime(QDateTime(at.year, at.month, at.day, at.hour, at.minute, 0))
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        hour, minute = task.schedule.hour_minute() if task.schedule.time else (9, 0)
        self.time.setTime(QTime(hour, minute))
        days_row = QWidget()
        days_layout = QHBoxLayout(days_row)
        days_layout.setContentsMargins(0, 0, 0, 0)
        self.day_boxes = {}
        for day in DAYS:
            box = QCheckBox(day.capitalize())
            box.setChecked(day in task.schedule.days)
            days_layout.addWidget(box)
            self.day_boxes[day] = box
        self.day_of_month = QSpinBox()
        self.day_of_month.setRange(1, 31)
        self.day_of_month.setValue(task.schedule.day_of_month or 1)
        form.addRow("Title", self.title)
        form.addRow("Repeat", self.repeat)
        form.addRow("Date and time (once)", self.when)
        form.addRow("Time of day", self.time)
        form.addRow("Days (weekly)", days_row)
        form.addRow("Day of month (monthly)", self.day_of_month)
        layout.addLayout(form)
        layout.addWidget(QLabel("Steps (remove any you no longer want):"))
        self.step_list = QListWidget()
        self.step_list.addItems([_step_text(s) for s in self.steps])
        layout.addWidget(self.step_list)
        remove = QPushButton("Remove selected step")
        remove.clicked.connect(self._remove_step)
        layout.addWidget(remove)
        self.error = QLabel()
        self.error.setProperty("error", True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.repeat.currentIndexChanged.connect(self._sync_fields)
        self._sync_fields()

    def _sync_fields(self) -> None:
        repeat = self.repeat.currentData()
        self.when.setEnabled(repeat == "none")
        self.time.setEnabled(repeat != "none")
        for box in self.day_boxes.values():
            box.setEnabled(repeat == "weekly")
        self.day_of_month.setEnabled(repeat == "monthly")

    def _remove_step(self) -> None:
        row = self.step_list.currentRow()
        if row >= 0 and len(self.steps) > 1:
            self.steps.pop(row)
            self.step_list.takeItem(row)

    def schedule_args(self) -> dict:
        when = self.when.dateTime().toPython()
        return {"repeat": self.repeat.currentData(),
                "when": when.isoformat() if self.repeat.currentData() == "none" else None,
                "time": self.time.time().toString("HH:mm"),
                "days": [d for d, box in self.day_boxes.items() if box.isChecked()],
                "day_of_month": self.day_of_month.value()}

    def _save(self) -> None:
        try:
            self.result_schedule = parse_schedule(self.schedule_args(),
                                                  datetime.now().astimezone())
        except ScheduleError as exc:
            self.error.setText(str(exc))
            return
        if not self.title.text().strip():
            self.error.setText("Title can't be empty.")
            return
        self.accept()


class RoutinesPage(SettingsPage):
    title = "Routines"
    _changed = Signal()

    def __init__(self, tasks, scheduler):
        super().__init__()
        self.tasks = tasks
        self.scheduler = scheduler
        layout = QVBoxLayout(self)
        layout.addWidget(hint(
            "Routines replay the actions Wisp resolved when you created them. Create them by "
            "voice, e.g. “every weekday at 9, open Outlook and Teams”. Missed runs: one-off tasks "
            "still run if Wisp starts within 12 hours; repeating ones run once if missed by less "
            "than an hour (change in settings.json → scheduler)."))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["On", "Title", "When", "Next run", "Last result"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for column, mode in ((0, QHeaderView.ResizeMode.ResizeToContents),
                             (1, QHeaderView.ResizeMode.Stretch),
                             (2, QHeaderView.ResizeMode.ResizeToContents),
                             (3, QHeaderView.ResizeMode.ResizeToContents),
                             (4, QHeaderView.ResizeMode.Stretch)):
            header.setSectionResizeMode(column, mode)
        self.table.itemChanged.connect(self._toggled)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        for label, slot in (("Edit…", self._edit), ("Run now", self._run_now),
                            ("Delete", self._delete), ("Refresh", self.refresh)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            if label == "Delete":
                button.setProperty("danger", True)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self._changed.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        tasks.subscribe(self._changed.emit)  # may fire on scheduler threads; queued to the UI
        self._task_ids: list[str] = []

    def refresh(self) -> None:
        tasks = self.tasks.list()
        self._task_ids = [t.id for t in tasks]
        self.table.blockSignals(True)
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            toggle = QTableWidgetItem()
            toggle.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            toggle.setCheckState(Qt.CheckState.Checked if task.enabled
                                 else Qt.CheckState.Unchecked)
            next_run = self.scheduler.next_run(task.id)
            values = [task.title, task.schedule.describe(),
                      next_run.strftime("%a %d %b %H:%M") if next_run else "—",
                      task.last_result or ""]
            self.table.setItem(row, 0, toggle)
            for column, value in enumerate(values, 1):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.blockSignals(False)

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._task_ids):
            return None
        return self.tasks.get(self._task_ids[row])

    def _toggled(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        task = self.tasks.get(self._task_ids[item.row()])
        if task is None:
            return
        enabled = item.checkState() == Qt.CheckState.Checked
        if enabled and task.schedule.one_off:
            when = datetime.fromisoformat(task.schedule.at)
            if when < datetime.now().astimezone():
                QMessageBox.information(self, "Routine", "That time has passed; edit the date "
                                        "first.")
                self.refresh()
                return
        self.scheduler.schedule(self.tasks.update(task.id, enabled=enabled))

    def _edit(self) -> None:
        task = self._selected()
        if task is None:
            return
        editor = TaskEditor(task, self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            updated = self.tasks.update(task.id, title=editor.title.text(),
                                        schedule=editor.result_schedule, steps=editor.steps,
                                        enabled=True)
            self.scheduler.schedule(updated)

    def _run_now(self) -> None:
        task = self._selected()
        if task is not None:
            self.scheduler.run_now(task.id)

    def _delete(self) -> None:
        task = self._selected()
        if task is None:
            return
        answer = QMessageBox.question(self, "Delete routine", f"Delete “{task.title}”?")
        if answer == QMessageBox.StandardButton.Yes:
            self.scheduler.unschedule(task.id)
            self.tasks.delete(task.id)
