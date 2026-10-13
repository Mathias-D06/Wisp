"""Settings → Hotkeys & audio: the three hold-chords with live conflict checks, hold time,
microphone and speaker (F11.4)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from wisp.audio import devices
from wisp.hotkeys.chords import find_conflicts, parse_chord
from wisp.settings import Settings
from wisp.ui.settings.base import SettingsPage, hint

HOTKEYS = [
    ("push_to_talk", "Push-to-talk", "Hold to talk to Wisp"),
    ("dictation", "Dictation", "Hold to dictate into the focused text box"),
    ("circle", "Circle to Ask", "Hold, then circle something on screen and ask"),
]
DEFAULT_DEVICE = "System default"


class HotkeysAudioPage(SettingsPage):
    title = "Hotkeys and audio"

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        keys = QGroupBox("Hold-to-use hotkeys")
        form = QFormLayout(keys)
        form.addRow(hint("Write keys joined with +, for example alt+win, ctrl+win, ctrl+shift or "
                         "ctrl+alt+space. Each works only while held on its own, so normal "
                         "shortcuts that share keys keep working."))
        self.edits: dict[str, QLineEdit] = {}
        for name, label, tip in HOTKEYS:
            edit = QLineEdit()
            edit.setToolTip(tip)
            edit.textChanged.connect(self._check)
            self.edits[name] = edit
            form.addRow(label, edit)
        self.hold_ms = QSpinBox()
        self.hold_ms.setRange(100, 2000)
        self.hold_ms.setSingleStep(50)
        self.hold_ms.setSuffix(" ms")
        form.addRow("Hold before it starts", self.hold_ms)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setProperty("error", True)
        form.addRow(self.problems)
        layout.addWidget(keys)

        audio = QGroupBox("Audio")
        audio_form = QFormLayout(audio)
        self.microphone = QComboBox()
        self.speaker = QComboBox()
        self.always_listening = QCheckBox("Always listening (no hotkey needed; use headphones "
                                          "so Wisp doesn't hear itself)")
        audio_form.addRow("Microphone", self.microphone)
        audio_form.addRow("Speaker", self.speaker)
        audio_form.addRow(self.always_listening)
        layout.addWidget(audio)
        layout.addStretch(1)

    def _check(self) -> None:
        chords = {label: self.edits[name].text() for name, label, _tip in HOTKEYS}
        problems = find_conflicts(chords)
        if not problems:
            # No problems means every chord parsed.
            shown = [f"{label}: {parse_chord(text).display()}" for label, text in chords.items()]
            self.problems.setProperty("error", False)
            self.problems.setText(" · ".join(shown))
        else:
            self.problems.setProperty("error", True)
            self.problems.setText("\n".join(problems))
        self.problems.style().unpolish(self.problems)
        self.problems.style().polish(self.problems)

    @staticmethod
    def _fill(combo: QComboBox, names: list[str], current: str) -> None:
        combo.clear()
        combo.addItem(DEFAULT_DEVICE, "")
        for name in names:
            combo.addItem(name, name)
        if current and current not in names:
            combo.addItem(f"{current} (not connected)", current)
        combo.setCurrentIndex(max(0, combo.findData(current)))

    def load(self, settings: Settings) -> None:
        for name, edit in self.edits.items():
            edit.setText(getattr(settings.hotkeys, name))
        self.hold_ms.setValue(settings.hotkeys.hold_ms)
        self._fill(self.microphone, [d.name for d in devices.input_devices()],
                   settings.audio.input_device)
        self._fill(self.speaker, [d.name for d in devices.output_devices()],
                   settings.audio.output_device)
        self.always_listening.setChecked(settings.audio.always_listening)
        self._check()

    def apply(self, settings: Settings) -> None:
        for name, edit in self.edits.items():
            setattr(settings.hotkeys, name, edit.text().strip().lower())
        settings.hotkeys.hold_ms = self.hold_ms.value()
        settings.audio.input_device = self.microphone.currentData() or ""
        settings.audio.output_device = self.speaker.currentData() or ""
        settings.audio.always_listening = self.always_listening.isChecked()
