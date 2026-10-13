"""The conversation: transcript rows and a composer (type, Talk, Send). Used by the island's
expanded panel and by the console window (the "Open in window" fallback); both follow the same
voice controller.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from wisp.ui import iconset, theme
from wisp.ui.transcript import TranscriptView
from wisp.ui.widgets import IconButton

MAX_ENTRIES = 200


class ChatPanel(QWidget):
    def __init__(self, voice, parent=None):
        super().__init__(parent)
        self.voice = voice
        self._entries: list[list] = []  # [role, text, final, turn, row]
        s = theme.SPACE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s["m"])

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self.view = TranscriptView()
        panel_layout.addWidget(self.view)
        layout.addWidget(panel, 1)

        composer = QFrame()
        composer.setObjectName("Composer")
        row = QHBoxLayout(composer)
        row.setContentsMargins(s["s"], s["xs"], s["xs"], s["xs"])
        row.setSpacing(s["xs"])
        self.input = QLineEdit()
        self.input.setObjectName("ComposerInput")
        self.input.setPlaceholderText("Type a request and press Enter")
        self.input.returnPressed.connect(self._send)
        self.talk = IconButton("mic", "Hold while you speak, or click once to start and again "
                               "to send", text="Talk")
        self.talk.pressed.connect(voice.talk_pressed)
        self.talk.released.connect(voice.talk_released)
        self.send = QPushButton("Send")
        self.send.setProperty("primary", True)
        self.send.setIconSize(QSize(theme.ICON_SM, theme.ICON_SM))
        self.send.clicked.connect(self._send)
        row.addWidget(self.input, 1)
        row.addWidget(self.talk)
        row.addWidget(self.send)
        layout.addWidget(composer)

        voice.transcript.connect(self.add)
        theme.signals.changed.connect(self.restyle)
        self.restyle()

    def restyle(self, _palette=None) -> None:
        p = theme.palette_for(self)
        r = theme.RADIUS_PANEL
        self.setStyleSheet(f"""
            QFrame#Panel {{ background: {p.surface}; border: 1px solid {p.hairline};
                border-radius: {r}px; }}
            QScrollArea#Transcript, QWidget#TranscriptContent {{ background: transparent; }}
            QFrame#Composer {{ background: {p.surface2}; border: 1px solid {p.hairline};
                border-radius: {r}px; }}
            QLineEdit#ComposerInput {{ background: transparent; border: none; padding: 6px 4px; }}
        """)
        self.send.setIcon(iconset.icon("send", p.accent_text))
        self.view.restyle()

    def _send(self) -> None:
        text = self.input.text()
        self.input.clear()
        self.voice.send_text(text)

    def add(self, role: str, text: str, final: bool, turn: int = 0) -> None:
        """One row per spoken turn: the user's words for turn N update the same row even after
        Wisp's answer has started; Wisp's partial answer updates its last unfinished row."""
        target = None
        if role == "user" and turn:
            target = next((e for e in reversed(self._entries)
                           if e[0] == "user" and e[3] == turn), None)
        elif role == "model":
            last = self._entries[-1] if self._entries else None
            if last and last[0] == "model" and not last[2]:
                target = last
        if target is not None:
            target[1], target[2] = text, final
            self.view.update_row(target[4], text, final)
            return
        row = self.view.add_row(role, text, final)
        self._entries.append([role, text, final, turn, row])
        if len(self._entries) > MAX_ENTRIES:
            del self._entries[:-MAX_ENTRIES]
            self.view.trim(MAX_ENTRIES)

    def last_reply(self) -> str:
        """Wisp's latest answer (for the expanded panel's live content)."""
        return next((e[1] for e in reversed(self._entries) if e[0] == "model"), "")
