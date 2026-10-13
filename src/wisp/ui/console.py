"""Console window: the island's "Open in window" fallback (D-045). Type instead of speaking,
see the transcript, mute the mic (D-043).

Layout: the orb and status on top with two icon toggles (always listening, mute) and a Retry
button that appears only after a voice error; below it the shared ChatPanel (transcript rows and
a composer with the text field, Talk and Send).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from wisp.ui import chrome, motion, theme
from wisp.ui.chat import ChatPanel
from wisp.ui.orb import Orb
from wisp.ui.widgets import IconButton


class ConsoleWindow(QWidget):
    def __init__(self, voice, accent: str):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("Window")
        self.setWindowTitle("Wisp")
        self.resize(560, 660)
        self.setMinimumSize(420, 420)
        chrome.prepare(self)
        self.voice = voice

        layout = QVBoxLayout(self)
        s = theme.SPACE
        layout.setContentsMargins(s["l"], s["m"], s["l"], s["l"])
        layout.setSpacing(s["m"])

        header = QHBoxLayout()
        header.setSpacing(s["m"])
        self.orb = Orb(44, accent)
        self.orb.clicked.connect(voice.toggle_talk)
        status_box = QVBoxLayout()
        status_box.setSpacing(0)
        self.status = QLabel("Ready")
        self.status.setProperty("heading", True)
        self.hint = QLabel("Click the orb or hold the talk keys to speak")
        self.hint.setProperty("caption", True)
        self.hint.setProperty("muted", True)
        status_box.addWidget(self.status)
        status_box.addWidget(self.hint)
        self.retry = QPushButton("Retry")
        self.retry.setToolTip("Connect to Gemini again")
        self.retry.clicked.connect(voice.retry)
        self.retry.setVisible(False)
        self.always = IconButton("listen", "Always listening (uses Gemini's voice detection; "
                                 "headphones recommended)", checkable=True)
        self.always.setChecked(voice.always_listening)
        self.always.toggled.connect(voice.set_always_listening)
        self.mute = IconButton("mic", "Mute microphone", checked_icon="mic-off", checkable=True)
        self.mute.setChecked(voice.mic.muted)
        self.mute.toggled.connect(voice.set_muted)
        header.addWidget(self.orb)
        header.addLayout(status_box, 1)
        header.addWidget(self.retry)
        header.addWidget(self.always)
        header.addWidget(self.mute)
        layout.addLayout(header)

        self.chat = ChatPanel(voice)
        layout.addWidget(self.chat, 1)
        self.view, self.input = self.chat.view, self.chat.input
        self.talk, self.send = self.chat.talk, self.chat.send

        voice.visual.connect(self._on_visual)
        theme.reveal_scrollbars(self)

    @property
    def _entries(self) -> list[list]:
        return self.chat._entries

    def add(self, role: str, text: str, final: bool, turn: int = 0) -> None:
        self.chat.add(role, text, final, turn)

    def set_accent(self, accent: str) -> None:
        self.orb.set_accent(accent)

    def _on_visual(self, state: str, level: float, text: str) -> None:
        self.orb.set_state(state, level)
        if self.status.text() != text:
            self.status.setText(text)
        self.retry.setVisible(self.voice.live_state == "error")
        if self.mute.isChecked() != self.voice.mic.muted:
            self.mute.blockSignals(True)
            self.mute.setChecked(self.voice.mic.muted)
            self.mute.blockSignals(False)
            self.mute.refresh()

    def sync_toggles(self, muted: bool, always_listening: bool) -> None:
        """Mirror changes made from the tray, the island or the Settings window."""
        for box, value in ((self.mute, muted), (self.always, always_listening)):
            box.blockSignals(True)
            box.setChecked(value)
            box.blockSignals(False)
            box.refresh()

    def open(self) -> None:
        first = not self.isVisible()
        self.show()
        chrome.apply(self)
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        if first:
            motion.window_fade(self, show=True)
