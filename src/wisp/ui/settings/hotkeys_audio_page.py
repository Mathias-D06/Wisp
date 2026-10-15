"""Settings → Hotkeys and audio: the three hold-chords with live conflict checks, hold time,
microphone and speaker (F11.4), a microphone test and the debug-audio switch (D-039)."""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from wisp.audio import INPUT_RATE, devices
from wisp.audio.capture import MicError
from wisp.audio.convert import has_speech, rms_dbfs
from wisp.audio.debug_wav import debug_dir, save_pcm
from wisp.hotkeys.chords import find_conflicts, parse_chord
from wisp.settings import Settings
from wisp.ui.settings.base import SettingsPage, hint

HOTKEYS = [
    ("push_to_talk", "Push-to-talk", "Hold to talk to Wisp"),
    ("dictation", "Dictation", "Hold to dictate into the focused text box"),
    ("circle", "Circle to Ask", "Hold, then circle something on screen and ask"),
    ("island", "Island", "Hold to open or close the Island"),
    ("screen_assist", "Screen Assist", "Hold to ask about the window in front (speak while "
     "holding, or just tap for a quick look)"),
    ("watch", "Watch mode", "Hold to turn Watch mode on or off"),
    ("discreet", "Discreet mode", "Hold to turn Discreet mode on or off"),
]
DEFAULT_DEVICE = "System default"
TEST_SECONDS = 3


class HotkeysAudioPage(SettingsPage):
    title = "Hotkeys and audio"

    def __init__(self, mic=None):
        super().__init__()
        self.mic = mic
        self._test_audio = bytearray()
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
        test_row = QHBoxLayout()
        self.test_button = QPushButton("Test microphone")
        self.test_button.setToolTip(f"Records {TEST_SECONDS} s from the saved microphone "
                                    "(Apply first if you changed it) and saves it to listen to")
        self.test_button.clicked.connect(self.start_mic_test)
        self.test_button.setEnabled(mic is not None)
        test_row.addWidget(self.test_button)
        test_row.addStretch(1)
        audio_form.addRow(test_row)
        self.test_result = QLabel()
        self.test_result.setWordWrap(True)
        audio_form.addRow(self.test_result)
        self.save_debug = QCheckBox("Save the audio and screenshots sent to Gemini "
                                    "(for troubleshooting)")
        self.save_debug.setToolTip("Each voice turn and dictation is saved as a WAV file, and "
                                   "each Screen Assist screenshot as a JPEG, in "
                                   "%APPDATA%\\Wisp\\debug (newest 20 of each kept)")
        debug_row = QHBoxLayout()
        debug_row.addWidget(self.save_debug, 1)
        open_folder = QPushButton("Open folder")
        open_folder.clicked.connect(lambda: os.startfile(str(debug_dir())))
        debug_row.addWidget(open_folder)
        audio_form.addRow(debug_row)
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
        self.save_debug.setChecked(settings.audio.save_debug_audio)
        self._check()

    def apply(self, settings: Settings) -> None:
        for name, edit in self.edits.items():
            setattr(settings.hotkeys, name, edit.text().strip().lower())
        settings.hotkeys.hold_ms = self.hold_ms.value()
        settings.audio.input_device = self.microphone.currentData() or ""
        settings.audio.output_device = self.speaker.currentData() or ""
        settings.audio.always_listening = self.always_listening.isChecked()
        settings.audio.save_debug_audio = self.save_debug.isChecked()

    # ----- microphone test ---------------------------------------------------------------------
    def start_mic_test(self) -> None:
        if self.mic is None:
            return
        try:
            self.mic.acquire("mic-test")
        except MicError as exc:
            self.test_result.setText(str(exc))
            return
        self._test_audio = bytearray()
        self.mic.subscribe("mic-test", self._test_audio.extend)
        self.test_button.setEnabled(False)
        self.test_result.setText(f"Recording for {TEST_SECONDS} s — say a short sentence…")
        QTimer.singleShot(TEST_SECONDS * 1000, self.finish_mic_test)

    def finish_mic_test(self) -> None:
        if self.mic is None:
            return
        channels = self.mic.channel_levels()
        source = self.mic.format_description
        self.mic.unsubscribe("mic-test")
        self.mic.release("mic-test")
        self.test_button.setEnabled(True)
        self.test_result.setText(describe_mic_test(bytes(self._test_audio), source, channels,
                                                   save_pcm("mic-test", bytes(self._test_audio))))


def describe_mic_test(pcm: bytes, source: str, channels: list[float], saved) -> str:
    """Plain-English result of a microphone test."""
    if not pcm:
        return "No audio arrived from the microphone. Check that it is connected and allowed."
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    level = rms_dbfs(samples)
    peak = 20 * np.log10(max(float(np.max(np.abs(samples))), 1e-6))
    if has_speech(pcm):
        verdict = "Speech heard — this is what Gemini receives."
    elif peak < -60:
        verdict = ("The microphone is silent. Check that it isn't muted (keyboard mute key, "
                   "Windows sound settings) and that the right microphone is selected.")
    else:
        verdict = ("Very quiet — no speech detected. Speak closer or raise the input level in "
                   "Windows Settings → System → Sound → Input.")
    parts = [verdict, f"Level {level:.0f} dBFS (peak {peak:.0f} dBFS), "
             f"{len(pcm) / (INPUT_RATE * 2):.1f} s."]
    if source:
        parts.append(f"Device format: {source}.")
    if len(channels) > 1:
        parts.append("Channels (dBFS): " + ", ".join(f"{c:.0f}" for c in channels) + ".")
    if saved is not None:
        parts.append(f"Saved as {saved.name} — Open folder to listen.")
    return " ".join(parts)

