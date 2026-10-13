"""Console window: type instead of speaking, see the transcript, mute the mic (D-043).

Layout: the orb and status on top with two icon toggles (always listening, mute) and a Retry
button that appears only after a voice error; the transcript as message rows in a panel; a
composer with the text field, Talk (hold, or click to start and click to send) and Send.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wisp.ui import chrome, iconset, motion, theme
from wisp.ui.orb import Orb
from wisp.ui.transcript import TranscriptView
from wisp.ui.widgets import IconButton

MAX_ENTRIES = 200


class ConsoleWindow(QWidget):
    def __init__(self, voice, accent: str):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("Window")
        self.setWindowTitle("Wisp")
        self.resize(560, 660)
        self.setMinimumSize(420, 420)
        chrome.prepare(self)
        self.voice = voice
        self._entries: list[list] = []  # [role, text, final, turn, row]

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
        voice.visual.connect(self._on_visual)
        theme.signals.changed.connect(self._restyle)
        self._restyle(theme.current())
        theme.reveal_scrollbars(self)

    # ----- theme ---------------------------------------------------------------------------
    def _restyle(self, p: theme.Palette) -> None:
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

    def set_accent(self, accent: str) -> None:
        self.orb.set_accent(accent)

    # ----- input ---------------------------------------------------------------------------
    def _send(self) -> None:
        text = self.input.text()
        self.input.clear()
        self.voice.send_text(text)

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

    # ----- transcript ------------------------------------------------------------------------
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

    def sync_toggles(self, muted: bool, always_listening: bool) -> None:
        """Mirror changes made from the tray or the Settings window."""
        for box, value in ((self.mute, muted), (self.always, always_listening)):
            box.blockSignals(True)
            box.setChecked(value)
            box.blockSignals(False)
            box.refresh()

    # ----- window ----------------------------------------------------------------------------
    def open(self) -> None:
        first = not self.isVisible()
        self.show()
        chrome.apply(self)
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        if first:
            motion.window_fade(self, show=True)
