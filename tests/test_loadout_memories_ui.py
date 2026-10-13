"""Settings → Loadout (F9) and Settings → Memories (F8.3)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from wisp.settings import SettingsStore, validate
from wisp.stores.memory import MemoryStore
from wisp.tools.registry import ToolRegistry

pytestmark = pytest.mark.qt


@pytest.fixture
def loadout(qtbot, tmp_path):
    from wisp.tools.builtin import memory as memory_tools
    from wisp.ui.settings.dialog import SettingsDialog
    from wisp.ui.settings.loadout_page import LoadoutPage

    registry = ToolRegistry()
    registry.register_all(memory_tools.tools())
    store = SettingsStore(tmp_path / "s.json")
    page = LoadoutPage(registry)
    dialog = SettingsDialog(store, [page])
    qtbot.addWidget(dialog)
    dialog.open_page("Loadout")
    return store, page, dialog


def test_loadout_round_trip(loadout):
    store, page, dialog = loadout
    assert page.voice.currentText() == "Zephyr" and page.custom.isHidden()
    assert page.skills["memory"].isChecked() and not page.skills["terminal"].isChecked()
    assert "remember" in page.skills["memory"].toolTip()
    assert "Safety" in page.skills["terminal"].toolTip()
    page.voice.setCurrentText("Kore")
    page.personality.setCurrentIndex(page.personality.findData("custom"))
    assert not page.custom.isHidden()
    page.custom.setPlainText("A dry butler who keeps it short.")
    page.theme.setCurrentIndex(page.theme.findData("light"))
    page.accent_buttons["#14b8a6"].click()
    page.skills["power"].setChecked(False)
    assert dialog.apply()
    saved = SettingsStore(store.path).get().loadout
    assert (saved.voice, saved.personality, saved.theme, saved.accent) == (
        "Kore", "custom", "light", "#14b8a6")
    assert saved.custom_personality == "A dry butler who keeps it short."
    assert "power" not in saved.skills and "memory" in saved.skills


def test_custom_accent_and_too_long_personality(loadout):
    _store, page, dialog = loadout
    page._set_accent("#ABCDEF")
    assert page.custom_accent.text() == "Custom #abcdef"
    assert not any(b.isChecked() for b in page.accent_buttons.values())
    page.personality.setCurrentIndex(page.personality.findData("custom"))
    page.custom.setPlainText("x" * 601)
    assert page.custom_count.text() == "601/600"
    assert not dialog.apply()
    assert "at most 600" in dialog.error.text()


def test_validate_loadout_values():
    from wisp.settings import Settings

    settings = Settings()
    settings.loadout.theme = "neon"
    settings.loadout.accent = "purple"
    settings.loadout.personality = "grumpy"
    problems = " ".join(validate(settings))
    assert "theme" in problems and "Accent" in problems and "personality" in problems


def test_personality_reaches_instruction():
    from datetime import datetime

    from wisp.live.config import system_instruction
    from wisp.settings import Settings

    settings = Settings()
    settings.loadout.personality = "custom"
    settings.loadout.custom_personality = "A pirate, briefly"
    assert "Personality: A pirate, briefly." in system_instruction(settings, [], datetime.now())
    settings.loadout.custom_personality = ""
    assert "warm, upbeat" in system_instruction(settings, [], datetime.now())  # fallback


def test_voice_and_skills_reach_live_config():
    from wisp.live.config import build_live_config
    from wisp.settings import Settings
    from wisp.tools.builtin import memory as memory_tools

    settings = Settings()
    settings.loadout.voice = "Puck"
    registry = ToolRegistry()
    registry.register_all(memory_tools.tools())
    config = build_live_config(settings, registry.declarations(settings), "x", None)
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Puck"
    assert {f.name for f in config.tools[0].function_declarations} == {
        "remember", "recall", "forget"}
    settings.loadout.skills.remove("memory")
    assert registry.declarations(settings) == []


# ----- Memories page -----------------------------------------------------------------------------
@pytest.fixture
def memories(qtbot, db):
    from wisp.ui.settings.memories_page import MemoriesPage

    store = MemoryStore(db)
    store.add("I live in Leeds")
    store.add("My sister Hana's birthday is 3 May")
    page = MemoriesPage(store)
    qtbot.addWidget(page)
    page.refresh()
    return page


def test_memories_list_search_add(memories):
    assert memories.table.rowCount() == 2
    assert memories.status.text() == "2 memories stored."
    memories.search.setText("birthday")
    assert memories.table.rowCount() == 1
    assert memories.table.item(0, 1).text().startswith("My sister")
    memories.search.clear()
    memories.new_fact.setText("I take my coffee black")
    memories._add()
    memories.refresh()
    assert memories.table.rowCount() == 3 and memories.new_fact.text() == ""


def test_memories_edit_pin_and_reject_empty(memories, qtbot):
    row = next(r for r in range(2) if "Leeds" in memories.table.item(r, 1).text())
    memory_id = memories._ids[row]
    memories.table.item(row, 1).setText("I live in York")
    assert memories.memory.get(memory_id).text == "I live in York"
    memories.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
    assert memories.memory.get(memory_id).pinned
    row = memories._ids.index(memory_id)
    memories.table.item(row, 1).setText("   ")
    assert memories.memory.get(memory_id).text == "I live in York"
    assert "Not saved" in memories.status.text()


def test_memories_delete_selected_and_all(memories, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    memories.table.selectRow(0)
    memories._delete_selected()
    assert memories.memory.count() == 1
    memories._clear()
    assert memories.memory.count() == 0
