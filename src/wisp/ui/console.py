"""Console window: type instead of speaking, see the transcript, mute the mic."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from wisp.ui.orb import Orb

MAX_ENTRIES = 200


class ConsoleWindow(QWidget):
    def __init__(self, voice, accent: str):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("Window")
        self.setWindowTitle("Wisp console")
        self.resize(560, 640)
        self.voice = voice
        self._entries: list[list] = []  # [role, text, final]

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.orb = Orb(40, accent)
        self.orb.clicked.connect(voice.toggle_talk)
        self.status = QLabel("Ready")
        self.status.setProperty("muted", True)
        self.mute = QCheckBox("Mute mic")
        self.mute.setChecked(voice.mic.muted)
        self.mute.toggled.connect(voice.set_muted)
        self.always = QCheckBox("Always listening")
        self.always.setChecked(voice.always_listening)
        self.always.setToolTip("Uses Gemini's voice activity detection. Headphones recommended.")
        self.always.toggled.connect(voice.set_always_listening)
        header.addWidget(self.orb)
        header.addWidget(self.status, 1)
        header.addWidget(self.always)
        header.addWidget(self.mute)
        layout.addLayout(header)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        layout.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a request and press Enter")
        self.input.returnPressed.connect(self._send)
        self.talk = QPushButton("Hold to talk")
        self.talk.pressed.connect(voice.ptt_press)
        self.talk.released.connect(voice.ptt_release)
        send = QPushButton("Send")
        send.setProperty("primary", True)
        send.clicked.connect(self._send)
        row.addWidget(self.input, 1)
        row.addWidget(self.talk)
        row.addWidget(send)
        layout.addLayout(row)

        voice.transcript.connect(self.add)
        voice.visual.connect(self._on_visual)

    def set_accent(self, accent: str) -> None:
        self.orb.set_accent(accent)

    def _send(self) -> None:
        text = self.input.text()
        self.input.clear()
        self.voice.send_text(text)

    def _on_visual(self, state: str, level: float, text: str) -> None:
        self.orb.set_state(state, level)
        self.status.setText(text)
        if self.mute.isChecked() != self.voice.mic.muted:
            self.mute.blockSignals(True)
            self.mute.setChecked(self.voice.mic.muted)
            self.mute.blockSignals(False)

    def add(self, role: str, text: str, final: bool) -> None:
        last = self._entries[-1] if self._entries else None
        if last and last[0] == role and not last[2] and role != "notice":
            last[1], last[2] = text, final
        else:
            self._entries.append([role, text, final])
            del self._entries[:-MAX_ENTRIES]
        self._render()

    def _render(self) -> None:
        labels = {"user": "You", "model": "Wisp", "notice": "Note"}
        parts = []
        for role, text, final in self._entries:
            muted = role == "notice" or not final
            style = "color:#9a9aae;" if muted else ""
            body = html.escape(text) if final else f"<i>{html.escape(text)}…</i>"
            parts.append(f'<p style="{style}"><b>{labels[role]}:</b> {body}</p>')
        self.view.setHtml("".join(parts))
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def sync_toggles(self, muted: bool, always_listening: bool) -> None:
        """Mirror changes made from the tray or the Settings window."""
        for box, value in ((self.mute, muted), (self.always, always_listening)):
            box.blockSignals(True)
            box.setChecked(value)
            box.blockSignals(False)

    def open(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
