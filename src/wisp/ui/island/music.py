"""Music strip: current media session with progress and transport buttons."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from wisp.system.media import MediaState
from wisp.ui.island.common import NEXT, PAUSE, PLAY, PREVIOUS, GlyphButton


class MediaSignals(QObject):
    """Delivers MediaWatcher updates (core asyncio thread) to the Qt thread."""

    changed = Signal(object)


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class MusicStrip(QFrame):
    def __init__(self, command):
        super().__init__()
        self.setObjectName("Card")
        self.command = command
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        text = QVBoxLayout()
        self.title = QLabel("Nothing playing")
        self.title.setObjectName("CardTitle")
        self.artist = QLabel("")
        self.artist.setObjectName("Hint")
        self.progress = QProgressBar()
        self.progress.setObjectName("Thin")
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.time = QLabel("")
        self.time.setObjectName("Hint")
        text.addWidget(self.title)
        text.addWidget(self.artist)
        text.addWidget(self.progress)
        layout.addLayout(text, 1)
        layout.addWidget(self.time, 0, Qt.AlignmentFlag.AlignBottom)
        self.previous = GlyphButton(PREVIOUS, "Previous")
        self.play = GlyphButton(PLAY, "Play/pause")
        self.next = GlyphButton(NEXT, "Next")
        for button, action in ((self.previous, "previous"), (self.play, "play_pause"),
                               (self.next, "next")):
            button.clicked.connect(lambda _c=False, a=action: self.command(a))
            layout.addWidget(button)
        self.show_state(MediaState())

    def show_state(self, state: MediaState) -> None:
        active = state.active
        self.title.setText(state.title or ("Nothing playing" if not active else "Unknown title"))
        self.artist.setText(state.artist)
        self.artist.setVisible(bool(state.artist))
        self.progress.setVisible(active and state.duration > 0)
        self.progress.setValue(int(state.progress * 1000))
        self.time.setText(f"{clock(state.position)} / {clock(state.duration)}"
                          if active and state.duration > 0 else "")
        self.play.set_icon_name(PAUSE if state.playing else PLAY)
        for button in (self.previous, self.play, self.next):
            button.setEnabled(active)
