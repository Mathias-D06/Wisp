from __future__ import annotations

import pytest

from wisp.keystore import KeyStore
from wisp.settings import SettingsStore

pytestmark = [pytest.mark.qt, pytest.mark.windows]


def test_general_page_round_trip(qtbot, tmp_path, monkeypatch):
    from wisp import startup
    from wisp.ui.settings.dialog import SettingsDialog
    from wisp.ui.settings.general_page import GeneralPage

    monkeypatch.setattr(startup, "is_enabled", lambda: False)
    store = SettingsStore(tmp_path / "s.json")
    page = GeneralPage(store, KeyStore(tmp_path / "k.bin"))
    dialog = SettingsDialog(store, [page])
    qtbot.addWidget(dialog)
    dialog.open_page("General")
    assert "No key stored" in page.key_status.text()
    page.idle_timeout.setValue(17)
    page.live_model.setText("gemini-test-live")
    assert dialog.apply()
    saved = SettingsStore(tmp_path / "s.json").get()
    assert saved.ai.idle_timeout_min == 17
    assert saved.ai.live_model == "gemini-test-live"


def test_invalid_settings_show_error(qtbot, tmp_path, monkeypatch):
    from wisp import startup
    from wisp.ui.settings.dialog import SettingsDialog
    from wisp.ui.settings.general_page import GeneralPage

    monkeypatch.setattr(startup, "is_enabled", lambda: False)
    store = SettingsStore(tmp_path / "s.json")
    page = GeneralPage(store, KeyStore(tmp_path / "k.bin"))
    dialog = SettingsDialog(store, [page])
    qtbot.addWidget(dialog)
    dialog.open_page()
    page.live_model.setText("   ")
    assert not dialog.apply()
    assert "Live model" in dialog.error.text()


def test_bad_key_is_rejected_before_network(qtbot, tmp_path, monkeypatch):
    from wisp import startup
    from wisp.ui.settings.general_page import GeneralPage

    monkeypatch.setattr(startup, "is_enabled", lambda: False)
    store = SettingsStore(tmp_path / "s.json")
    page = GeneralPage(store, KeyStore(tmp_path / "k.bin"))
    qtbot.addWidget(page)
    page.key_edit.setText("nope")
    page._test_and_save()
    assert "does not look like" in page.key_message.text()
