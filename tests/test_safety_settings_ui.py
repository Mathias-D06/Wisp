"""Settings → Safety, Hotkeys and audio, Action log (F11.4, F12.3, F12.5) and key test-on-save
(F11.2)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QMessageBox

from wisp.audio.devices import AudioDevice
from wisp.keystore import KeyStore
from wisp.settings import SettingsStore
from wisp.stores.action_log import ActionLog
from wisp.tools.registry import ToolRegistry

pytestmark = pytest.mark.qt
FAKE_KEY = "AIza" + "A1b2C3d4E5" * 3 + "xyzQW"


def _full_registry() -> ToolRegistry:
    from wisp.tools.builtin import raw_input, system, terminal, todos, windows

    registry = ToolRegistry()
    for module in (windows, todos, system, terminal, raw_input):
        registry.register_all(module.tools())
    return registry


@pytest.fixture
def dialog(qtbot, tmp_path, monkeypatch):
    from wisp.audio import devices
    from wisp.ui.settings.dialog import SettingsDialog
    from wisp.ui.settings.hotkeys_audio_page import HotkeysAudioPage
    from wisp.ui.settings.loadout_page import LoadoutPage
    from wisp.ui.settings.safety_page import SafetyPage

    monkeypatch.setattr(devices, "input_devices",
                        lambda: [AudioDevice(1, "Headset Microphone", False),
                                 AudioDevice(2, "Array Microphone", True)])
    monkeypatch.setattr(devices, "output_devices",
                        lambda: [AudioDevice(3, "Speakers", True)])
    registry = _full_registry()
    store = SettingsStore(tmp_path / "s.json")
    pages = {"loadout": LoadoutPage(registry), "hotkeys": HotkeysAudioPage(),
             "safety": SafetyPage(registry)}
    window = SettingsDialog(store, list(pages.values()))
    qtbot.addWidget(window)
    window.open_page("Safety")
    window.store, window.pages = store, pages
    return window


def test_safety_toggle_also_ticks_skill_and_loadout_follows(dialog):
    safety, loadout = dialog.pages["safety"], dialog.pages["loadout"]
    assert not safety.toggles["allow_terminal"].isChecked()
    assert not loadout.skills["terminal"].isChecked()
    safety.toggles["allow_terminal"].setChecked(True)
    assert dialog.apply()
    saved = SettingsStore(dialog.store.path).get()
    assert saved.safety.allow_terminal and "terminal" in saved.loadout.skills
    assert loadout.skills["terminal"].isChecked()  # reloaded after Apply
    loadout.skills["terminal"].setChecked(False)  # the user can still switch the skill off
    assert dialog.apply()
    saved = SettingsStore(dialog.store.path).get()
    assert saved.safety.allow_terminal and "terminal" not in saved.loadout.skills


def test_auto_approve_choices_exclude_never_list(dialog):
    safety = dialog.pages["safety"]
    assert set(safety.auto) == {"close_window", "delete_todo", "toggle_setting"}
    labels = " ".join(label.text() for label in safety.findChildren(QLabel))
    assert "Always ask, whatever you choose:" in labels
    assert "press a key or shortcut in the active window" in labels
    safety.auto["delete_todo"].setChecked(True)
    safety.taint_minutes.setValue(15)
    assert dialog.apply()
    saved = SettingsStore(dialog.store.path).get().safety
    assert saved.auto_approve == ["delete_todo"] and saved.taint_minutes == 15


def test_hand_edited_never_entries_are_dropped(dialog):
    dialog.store.update(lambda s: s.safety.auto_approve.extend(["close_window"]))
    raw = dialog.store.path.read_text(encoding="utf-8").replace(
        '"close_window"', '"close_window", "power"')
    dialog.store.path.write_text(raw, encoding="utf-8")
    store = SettingsStore(dialog.store.path)
    assert "power" in store.get().safety.auto_approve
    dialog._store = store
    dialog.open_page("Safety")
    assert dialog.apply()
    assert SettingsStore(store.path).get().safety.auto_approve == ["close_window"]


def test_hotkeys_live_conflicts_and_audio(dialog):
    page = dialog.pages["hotkeys"]
    assert page.problems.text().startswith("Push-to-talk: Alt + Win")
    page.edits["dictation"].setText("alt+win")
    assert "same keys" in page.problems.text()
    page.edits["dictation"].setText("ctrl+alt+x")
    page.edits["circle"].setText("ctrl+banana")
    assert "Unknown key 'banana'" in page.problems.text()
    assert not dialog.apply()
    page.edits["circle"].setText("ctrl+shift")
    assert [page.microphone.itemText(i) for i in range(page.microphone.count())] == [
        "System default", "Headset Microphone", "Array Microphone"]
    page.microphone.setCurrentIndex(1)
    page.hold_ms.setValue(400)
    assert dialog.apply()
    saved = SettingsStore(dialog.store.path).get()
    assert saved.hotkeys.dictation == "ctrl+alt+x" and saved.hotkeys.hold_ms == 400
    assert saved.audio.input_device == "Headset Microphone" and saved.audio.output_device == ""


def test_missing_audio_device_is_kept_and_labelled(dialog):
    dialog.store.update(lambda s: setattr(s.audio, "output_device", "USB DAC"))
    dialog.open_page("Hotkeys and audio")
    speaker = dialog.pages["hotkeys"].speaker
    assert speaker.currentText() == "USB DAC (not connected)"
    assert dialog.apply()
    assert SettingsStore(dialog.store.path).get().audio.output_device == "USB DAC"


# ----- Action log page ----------------------------------------------------------------------------
@pytest.fixture
def log_page(qtbot, db):
    from wisp.ui.settings.action_log_page import ActionLogPage

    log = ActionLog(db)
    log.record(origin="voice", tool="open_app", args={"name": "Spotify"}, decision="allow",
               result={"ok": True, "opened": "Spotify"}, ok=True)
    log.record(origin="voice", tool="run_command", args={"command": "dir"}, decision="deny",
               result={"ok": False, "error": "disabled"}, ok=False)
    log.record(origin="voice", tool="close_window", args={"name": "Notepad"},
               decision="confirm-requested", result={"status": "needs_confirmation"}, ok=False)
    log.record(origin="schedule", tool="open_app", args={"name": "Teams"},
               decision="allow", result={"ok": False, "error": "not found"}, ok=False)
    page = ActionLogPage(log)
    qtbot.addWidget(page)
    page.refresh()
    return page


def test_action_log_lists_filters_and_details(log_page):
    assert log_page.table.rowCount() == 4
    assert log_page.table.item(0, 2).text() == "open_app"  # newest first
    assert log_page.table.item(0, 4).text().startswith("✗")
    log_page.search.setText("spotify")
    assert log_page.table.rowCount() == 1
    log_page.search.clear()
    log_page.problems.setChecked(True)
    assert sorted(log_page.table.item(r, 2).text() for r in range(log_page.table.rowCount())) \
        == ["open_app", "run_command"]  # failed + denied; pending confirmation isn't a problem
    log_page.table.setCurrentCell(0, 0)
    assert "Arguments:" in log_page.details.toPlainText()


def test_action_log_clear_asks(log_page, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    log_page._clear()
    assert log_page.table.rowCount() == 4
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    log_page._clear()
    assert log_page.table.rowCount() == 0 and log_page.action_log.recent() == []


# ----- F11.2: key tested before it is stored ------------------------------------------------------
@pytest.mark.windows
def test_key_is_tested_before_saving(qtbot, tmp_path, monkeypatch):
    from wisp import startup
    from wisp.ai.gemini import KeyCheck
    from wisp.ui.settings import general_page
    from wisp.ui.settings.general_page import GeneralPage

    monkeypatch.setattr(startup, "is_enabled", lambda: False)
    checked = []

    def fake_validate(key, live, text):
        checked.append((key, live, text))
        return KeyCheck(len(checked) > 1, "Key works." if len(checked) > 1 else "Key rejected.")

    monkeypatch.setattr(general_page, "validate_key", fake_validate)
    keystore = KeyStore(tmp_path / "k.bin")
    page = GeneralPage(SettingsStore(tmp_path / "s.json"), keystore)
    qtbot.addWidget(page)
    page.load(SettingsStore(tmp_path / "s.json").get())
    page.key_edit.setText(FAKE_KEY)
    page._test_and_save()
    qtbot.waitUntil(lambda: page.key_message.text() == "Key rejected.", timeout=3000)
    assert keystore.get() is None and not page.save_anyway_button.isHidden()
    page._test_and_save()
    qtbot.waitUntil(lambda: page.key_message.text() == "Key works.", timeout=3000)
    assert keystore.get() == FAKE_KEY and page.key_edit.text() == ""
    assert checked[0][1:] == ("gemini-3.8-live", "gemini-3.8-flash")
    assert FAKE_KEY not in page.key_status.text()  # shown masked only
