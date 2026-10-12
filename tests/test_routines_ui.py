from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from wisp.scheduling.spec import Schedule
from wisp.scheduling.tasks import TaskStore

pytestmark = pytest.mark.qt


class FakeScheduler:
    def __init__(self):
        self.scheduled, self.removed = [], []

    def schedule(self, task):
        self.scheduled.append((task.id, task.enabled))

    def unschedule(self, task_id):
        self.removed.append(task_id)

    def next_run(self, task_id):
        return None

    def run_now(self, task_id):
        self.scheduled.append(("run", task_id))


@pytest.fixture
def page(qtbot, db):
    from wisp.ui.settings.routines_page import RoutinesPage

    store = TaskStore(db)
    store.add("Morning apps", Schedule(repeat="daily", time="09:00"),
              [{"tool": "open_app", "args": {"name": "Unity"}},
               {"tool": "open_app", "args": {"name": "Spotify"}}])
    widget = RoutinesPage(store, FakeScheduler())
    qtbot.addWidget(widget)
    widget.refresh()
    return widget


def test_lists_and_toggles(page):
    assert page.table.rowCount() == 1
    assert page.table.item(0, 2).text() == "every day at 09:00"
    page.table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    task_id = page._task_ids[0]
    assert page.scheduler.scheduled == [(task_id, False)]
    assert page.tasks.get(task_id).enabled is False


def test_edit_changes_schedule_and_removes_step(page, monkeypatch):
    from wisp.ui.settings import routines_page

    def fake_exec(editor):
        editor.repeat.setCurrentIndex(routines_page.REPEATS.index("weekdays"))
        editor.step_list.setCurrentRow(0)
        editor._remove_step()
        editor._save()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(routines_page.TaskEditor, "exec", fake_exec)
    page.table.selectRow(0)
    page._edit()
    task = page.tasks.get(page._task_ids[0])
    assert task.schedule.describe() == "weekdays at 09:00"
    assert task.steps == [{"tool": "open_app", "args": {"name": "Spotify"}}]


def test_delete_asks_first(page, monkeypatch):
    page.table.selectRow(0)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)
    page._delete()
    assert len(page.tasks.list()) == 1
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    page._delete()
    assert page.tasks.list() == []
