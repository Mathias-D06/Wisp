from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from wisp.stores.todos import TodoStore
from wisp.tools.base import Risk, ToolContext, ToolError
from wisp.tools.builtin import todos as todo_tools

TZ = UTC


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 12, 9, 0, tzinfo=TZ)

    def __call__(self):
        return self.now


@pytest.fixture
def store(db):
    return TodoStore(db, Clock())


def test_add_list_complete_delete(store):
    a = store.add("Buy milk")
    b = store.add("Call Sam", due_at=datetime(2026, 10, 12, 15, 0, tzinfo=TZ))
    assert b.remind and not a.remind
    assert [t.text for t in store.list()] == ["Call Sam", "Buy milk"]  # due first
    store.set_done(a.id)
    assert [t.text for t in store.list()] == ["Call Sam"]
    assert len(store.list(include_done=True)) == 2
    store.delete(b.id)
    assert store.list() == []
    with pytest.raises(ValueError):
        store.add("   ")


def test_find_by_words_or_id(store):
    store.add("Renew passport")
    todo = store.add("Water the plants")
    assert store.find("plants").id == todo.id
    assert store.find(str(todo.id)).id == todo.id
    assert store.find("completely unrelated thing") is None


def test_reminders_fire_once(store):
    clock = store._now
    todo = store.add("Stand-up", due_at=clock.now + timedelta(minutes=5))
    assert store.due_reminders() == []
    clock.now += timedelta(minutes=6)
    assert [t.id for t in store.due_reminders()] == [todo.id]
    store.mark_reminded(todo.id)
    assert store.due_reminders() == []
    assert [t.text for t in store.due_today()] == ["Stand-up"]


def test_update_resets_reminder(store):
    clock = store._now
    todo = store.add("Pay rent", due_at=clock.now + timedelta(minutes=1))
    store.mark_reminded(todo.id)
    store.update(todo.id, due_at=clock.now + timedelta(hours=2))
    assert store.get(todo.id).reminded is False


def test_tools(store):
    ctx = ToolContext("voice", SimpleNamespace(todos=store))
    added = todo_tools.add_todo(ctx, {"text": "Book dentist", "due": "2026-10-13T10:00"})
    assert added["reminder"] is True and added["added"]["due"].startswith("2026-10-13T10:00")
    assert todo_tools.list_todos(ctx, {})["todos"][0]["text"] == "Book dentist"
    assert todo_tools.complete_todo(ctx, {"todo": "dentist"}) == {"completed": "Book dentist"}
    with pytest.raises(ToolError):
        todo_tools.complete_todo(ctx, {"todo": "dentist"})  # no open match any more
    delete = next(t for t in todo_tools.tools() if t.name == "delete_todo")
    assert delete.risk == Risk.CONFIRM
