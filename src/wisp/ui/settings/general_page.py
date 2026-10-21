"""General settings: API key, models, language, idle timeout, start-up, and (in an installed
copy) Uninstall."""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from wisp import startup, uninstall
from wisp.ai.gemini import validate_key
from wisp.keystore import KeyStore, looks_like_key, mask
from wisp.settings import LANGUAGE_CODES, Settings, SettingsStore
from wisp.ui.settings.base import SettingsPage, hint

LANGUAGES = [name for name in LANGUAGE_CODES if name != "English"]
# Text models that read images and take thinking_level "low" (ai.google.dev/gemini-api/docs/
# models and /thinking, 2026-10-20); any other name can be typed in (D-057)
FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite"]


def fallback_name(combo: QComboBox) -> str:
    """The fallback model chosen ("" for Off), whether picked from the list or typed."""
    text = combo.currentText().strip()
    if text == combo.itemText(0):  # "Off"
        return ""
    index = combo.findText(text)
    return (combo.itemData(index) or "") if index >= 0 else text


class _KeyCheckBridge(QObject):
    finished = Signal(bool, str, str)  # ok, message, key


class GeneralPage(SettingsPage):
    title = "General"

    def __init__(self, store: SettingsStore, keystore: KeyStore,
                 uninstall_app: Callable[[], None] | None = None,
                 uninstaller: Callable[[], object] = uninstall.uninstaller_path):
        """``uninstall_app`` closes Wisp and starts its uninstaller (D-061); the button shows
        only when ``uninstaller()`` finds one, i.e. in an installed copy."""
        super().__init__()
        self._store = store
        self._keystore = keystore
        self._uninstall_app = uninstall_app
        self._bridge = _KeyCheckBridge()
        self._bridge.finished.connect(self._on_key_checked)
        self._pending_key: str | None = None

        layout = QVBoxLayout(self)

        key_box = QGroupBox("Gemini API key")
        key_layout = QVBoxLayout(key_box)
        self.key_status = QLabel()
        key_layout.addWidget(self.key_status)
        row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Paste a new key to replace the stored one")
        self.save_key_button = QPushButton("Save and test")
        self.save_key_button.setProperty("primary", True)
        self.save_key_button.clicked.connect(self._test_and_save)
        self.save_anyway_button = QPushButton("Save without test")
        self.save_anyway_button.setVisible(False)
        self.save_anyway_button.clicked.connect(self._save_anyway)
        self.remove_key_button = QPushButton("Remove key")
        self.remove_key_button.setProperty("danger", True)
        self.remove_key_button.clicked.connect(self._remove_key)
        row.addWidget(self.key_edit, 1)
        row.addWidget(self.save_key_button)
        row.addWidget(self.save_anyway_button)
        row.addWidget(self.remove_key_button)
        key_layout.addLayout(row)
        self.key_message = QLabel()
        self.key_message.setWordWrap(True)
        key_layout.addWidget(self.key_message)
        key_hint = hint(
            'Get a key at <a href="https://aistudio.google.com/api-keys">'
            "aistudio.google.com/api-keys</a>. In the UK, EEA and Switzerland Google requires a "
            "key from a billing-enabled project. The key is encrypted with Windows DPAPI "
            "for your user account and never shown in full."
        )
        key_hint.setOpenExternalLinks(True)
        key_layout.addWidget(key_hint)
        layout.addWidget(key_box)

        ai_box = QGroupBox("Assistant")
        form = QFormLayout(ai_box)
        self.live_model = QLineEdit()
        self.text_model = QLineEdit()
        self.fallback_model = QComboBox()
        self.fallback_model.setEditable(True)
        self.fallback_model.addItem("Off", "")
        for name in FALLBACK_MODELS:
            self.fallback_model.addItem(name, name)
        self.fallback_model.setToolTip(
            "Used only when the text model is still overloaded (“high demand”) after "
            "Wisp has retried. Screen Assist then says which model answered.")
        self.language = QComboBox()
        self.language.setEditable(True)
        self.language.addItems(LANGUAGES)
        self.idle_timeout = QSpinBox()
        self.idle_timeout.setRange(1, 240)
        self.idle_timeout.setSuffix(" min")
        form.addRow("Live (voice) model", self.live_model)
        form.addRow("Text model (dictation, Screen Assist)", self.text_model)
        form.addRow("Fallback text model (when busy)", self.fallback_model)
        form.addRow("Language", self.language)
        form.addRow("Close idle voice session after", self.idle_timeout)
        layout.addWidget(ai_box)

        app_box = QGroupBox("App")
        app_form = QFormLayout(app_box)
        self.start_with_windows = QCheckBox("Start Wisp when I sign in to Windows")
        self.show_island = QCheckBox("Show the Island at the top of the screen")
        self.island_monitor = QComboBox()
        self.island_monitor.addItem("Main display", "primary")
        self.island_monitor.addItem("The display with the pointer", "cursor")
        self.island_hide = QCheckBox("Hide the Island when nothing is happening")
        self.island_hide.setToolTip("It slides up out of view; move the pointer to the top edge "
                                    "of the screen, above where it was, to bring it back")
        self.island_hide_after = QSpinBox()
        self.island_hide_after.setRange(3, 15)
        self.island_hide_after.setSuffix(" s")
        self.island_hide.toggled.connect(self.island_hide_after.setEnabled)
        self.island_keep_music = QCheckBox("Keep it visible while music plays")
        self.clipboard_size = QSpinBox()
        self.clipboard_size.setRange(5, 500)
        self.typing_wpm = QSpinBox()
        self.typing_wpm.setRange(10, 200)
        self.typing_wpm.setSuffix(" words/min")
        app_form.addRow(self.start_with_windows)
        app_form.addRow(self.show_island)
        app_form.addRow("Island on", self.island_monitor)
        app_form.addRow(self.island_hide)
        app_form.addRow("Hide after", self.island_hide_after)
        app_form.addRow(self.island_keep_music)
        app_form.addRow("Clipboard history items", self.clipboard_size)
        app_form.addRow("Your typing speed (for Stats)", self.typing_wpm)
        self.uninstall_button = QPushButton("Uninstall Wisp…")
        self.uninstall_button.setToolTip(
            "Closes Wisp and starts its uninstaller, which asks before removing anything and "
            "whether to delete your data too")
        self.uninstall_button.clicked.connect(self._confirm_uninstall)
        installed = uninstall_app is not None and uninstaller() is not None
        self.uninstall_button.setVisible(installed)
        app_form.addRow(self.uninstall_button)
        layout.addWidget(app_box)
        layout.addStretch(1)
        self._show_key_status()

    def _show_key_status(self) -> None:
        key = self._keystore.get()
        if key:
            self.key_status.setText(f"Stored key: {mask(key)}")
        else:
            self.key_status.setText("No key stored. AI features are off until you add one.")
        self.remove_key_button.setEnabled(bool(key))

    def _set_message(self, text: str, kind: str) -> None:
        self.key_message.setText(text)
        self.key_message.setProperty("error", kind == "error")
        self.key_message.setProperty("ok", kind == "ok")
        self.key_message.style().unpolish(self.key_message)
        self.key_message.style().polish(self.key_message)

    def _test_and_save(self) -> None:
        key = self.key_edit.text().strip()
        if not looks_like_key(key):
            self._set_message("That does not look like an API key.", "error")
            return
        self._pending_key = key
        self.save_key_button.setEnabled(False)
        self.save_anyway_button.setVisible(False)
        self._set_message("Testing the key with Google…", "info")
        live_model = self.live_model.text().strip()
        text_model = self.text_model.text().strip()

        def worker() -> None:
            result = validate_key(key, live_model, text_model)
            self._bridge.finished.emit(result.ok, result.message, key)

        threading.Thread(target=worker, name="key-check", daemon=True).start()

    def _on_key_checked(self, ok: bool, message: str, key: str) -> None:
        self.save_key_button.setEnabled(True)
        if key != self._pending_key:
            return
        if ok:
            self._keystore.set(key)
            self.key_edit.clear()
            self._set_message(message, "ok")
        else:
            self._set_message(message, "error")
            self.save_anyway_button.setVisible(True)
        self._show_key_status()

    def _save_anyway(self) -> None:
        key = self.key_edit.text().strip()
        if looks_like_key(key):
            self._keystore.set(key)
            self.key_edit.clear()
            self._set_message("Key saved without a successful test.", "info")
        self.save_anyway_button.setVisible(False)
        self._show_key_status()

    def _confirm_uninstall(self) -> None:
        answer = QMessageBox.question(
            self, "Uninstall Wisp",
            "Wisp will close and its uninstaller will start. The uninstaller asks once more "
            "before removing anything, and whether to delete your Wisp data (settings, API "
            "key, memories, logs) too.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes and self._uninstall_app is not None:
            self._uninstall_app()

    def _remove_key(self) -> None:
        self._keystore.clear()
        self._set_message("Key removed.", "info")
        self._show_key_status()

    def load(self, settings: Settings) -> None:
        self.live_model.setText(settings.ai.live_model)
        self.text_model.setText(settings.ai.text_model)
        index = self.fallback_model.findData(settings.ai.fallback_text_model)
        if index >= 0:
            self.fallback_model.setCurrentIndex(index)
        else:
            self.fallback_model.setEditText(settings.ai.fallback_text_model)
        self.language.setCurrentText(settings.ai.language)
        self.idle_timeout.setValue(settings.ai.idle_timeout_min)
        self.start_with_windows.setChecked(startup.is_enabled())
        self.show_island.setChecked(settings.general.show_island)
        index = self.island_monitor.findData(settings.general.island_monitor)
        self.island_monitor.setCurrentIndex(max(0, index))
        self.island_hide.setChecked(settings.general.island_hide_when_idle)
        self.island_hide_after.setValue(settings.general.island_hide_after_s)
        self.island_hide_after.setEnabled(settings.general.island_hide_when_idle)
        self.island_keep_music.setChecked(settings.general.island_keep_for_music)
        self.clipboard_size.setValue(settings.general.clipboard_history_size)
        self.typing_wpm.setValue(settings.general.typing_wpm)
        self._show_key_status()

    def apply(self, settings: Settings) -> None:
        settings.ai.live_model = self.live_model.text().strip()
        settings.ai.text_model = self.text_model.text().strip()
        settings.ai.fallback_text_model = fallback_name(self.fallback_model)
        settings.ai.language = self.language.currentText().strip() or "English (UK)"
        settings.ai.idle_timeout_min = self.idle_timeout.value()
        settings.general.start_with_windows = self.start_with_windows.isChecked()
        settings.general.show_island = self.show_island.isChecked()
        settings.general.island_monitor = self.island_monitor.currentData() or "primary"
        settings.general.island_hide_when_idle = self.island_hide.isChecked()
        settings.general.island_hide_after_s = self.island_hide_after.value()
        settings.general.island_keep_for_music = self.island_keep_music.isChecked()
        settings.general.clipboard_history_size = self.clipboard_size.value()
        settings.general.typing_wpm = self.typing_wpm.value()
