"""The island's expanded panel (D-045): live status, now playing, and the tabs: Chat (the
conversation and a text box, replacing the console window), Controls, Today, Stats, Clipboard,
Apps, Wallpaper and Power.

The panel is a normal widget tree inside the island's canvas. While the island morphs, the island
paints a snapshot of it instead (``rows`` gives the bands that fade in one after another).
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wisp.ui import motion, theme
from wisp.ui.chat import ChatPanel
from wisp.ui.island.music import MusicStrip
from wisp.ui.orb import Orb
from wisp.ui.widgets import IconButton


def island_stylesheet(p: theme.Palette) -> str:
    """Panel styles from the theme tokens (D-043), on the island's black fill."""
    r, rc = theme.RADIUS_PANEL, theme.RADIUS_CONTROL
    return f"""
    QWidget#IslandPanel, QStackedWidget#IslandStack {{ background: transparent; }}
    QLabel {{ background: transparent; }}
    QLabel#Status {{ {theme.font_css(theme.BODY)} }}
    QLabel#Section {{ color: {p.secondary}; {theme.font_css(theme.CAPTION)} margin-top: 6px; }}
    QLabel#Hint {{ color: {p.muted}; {theme.font_css(theme.CAPTION)} }}
    QLabel#CardTitle {{ color: {p.text}; }}
    QLabel#Big {{ {theme.font_css(theme.TITLE)} font-weight: {theme.SEMIBOLD}; }}
    QFrame#Card {{ background: {p.surface}; border: 1px solid {p.hairline};
        border-radius: {r}px; }}
    QPushButton#Tab {{ background: transparent; border: none; color: {p.secondary};
        padding: 6px 10px; border-radius: {rc}px; }}
    QPushButton#Tab:checked {{ background: {p.surface2}; color: {p.text}; }}
    QPushButton#Tab:hover {{ color: {p.text}; background: {p.hover}; }}
    QPushButton#Chip {{ background: {p.surface}; border: 1px solid {p.hairline};
        border-radius: {r}px; padding: 8px 12px; text-align: left; }}
    QPushButton#Chip:hover {{ background: {p.hover}; }}
    QPushButton#Chip:checked {{ background: {p.accent_soft}; color: {p.text};
        border: 1px solid {theme.rgba(p.accent, 0.55)}; }}
    QPushButton#Chip:disabled {{ color: {p.muted}; }}
    QPushButton#KeyPrompt {{ background: {p.accent_fill}; color: {p.accent_text}; border: none;
        border-radius: {rc}px; padding: 4px 10px; }}
    QPushButton#Flat {{ background: transparent; border: none; color: {p.secondary};
        padding: 4px 8px; border-radius: {rc}px; }}
    QPushButton#Flat:hover {{ background: {p.hover}; color: {p.text}; }}
    QListWidget#Flat {{ background: transparent; border: none; }}
    QListWidget#Flat::item {{ padding: 6px; border-radius: {rc}px; }}
    QListWidget#Flat::item:hover {{ background: {p.hover}; }}
    QListWidget#Flat::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
    QProgressBar#Thin {{ background: {p.border}; border: none; border-radius: 2px; }}
    QProgressBar#Thin::chunk {{ background: {p.accent}; border-radius: 2px; }}
    """


class ExpandedPanel(QWidget):
    settings_requested = Signal(str)
    console_requested = Signal()

    def __init__(self, voice, accent: str, has_key, media_command, tabs: list, parent=None):
        super().__init__(parent)
        self.setObjectName("IslandPanel")
        self.voice = voice
        self.has_key = has_key
        s = theme.SPACE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s["l"], s["m"], s["l"], s["l"])
        layout.setSpacing(s["s"])

        self.header = QWidget()
        bar = QHBoxLayout(self.header)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(s["s"])
        self.orb = Orb(28, accent)
        self.orb.clicked.connect(voice.toggle_talk)
        self.status = QLabel("Ready")
        self.status.setObjectName("Status")
        self.key_prompt = QPushButton("Add your API key")
        self.key_prompt.setObjectName("KeyPrompt")
        self.key_prompt.clicked.connect(lambda: self.settings_requested.emit("General"))
        self.retry = QPushButton("Retry")
        self.retry.setObjectName("Flat")
        self.retry.clicked.connect(voice.retry)
        self.retry.setVisible(False)
        self.always = IconButton("listen", "Always listening (uses Gemini's voice detection; "
                                 "headphones recommended)", checkable=True)
        self.always.setChecked(voice.always_listening)
        self.always.toggled.connect(voice.set_always_listening)
        self.mute = IconButton("mic", "Mute microphone", checked_icon="mic-off", checkable=True)
        self.mute.setChecked(voice.mic.muted)
        self.mute.toggled.connect(voice.set_muted)
        self.open_window = QPushButton("Open in window")
        self.open_window.setObjectName("Flat")
        self.open_window.setToolTip("Show the conversation in a normal window")
        self.open_window.clicked.connect(self.console_requested.emit)
        self.settings_button = IconButton("settings", "Settings")
        self.settings_button.clicked.connect(lambda: self.settings_requested.emit(""))
        bar.addWidget(self.orb)
        bar.addWidget(self.status, 1)
        for widget in (self.key_prompt, self.retry, self.always, self.mute, self.open_window,
                       self.settings_button):
            bar.addWidget(widget)
        layout.addWidget(self.header)

        self.music = MusicStrip(media_command)
        self.music.setVisible(False)
        layout.addWidget(self.music)

        self.tab_bar = QWidget()
        tab_row = QHBoxLayout(self.tab_bar)
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(2)
        self.tab_group = QButtonGroup(self)
        self.stack = QStackedWidget()
        self.stack.setObjectName("IslandStack")
        self.chat = ChatPanel(voice)
        self.tabs = [("Chat", self.chat), *tabs]
        for index, (name, widget) in enumerate(self.tabs):
            button = QPushButton(name)
            button.setObjectName("Tab")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tab_group.addButton(button, index)
            tab_row.addWidget(button)
            self.stack.addWidget(widget)
        tab_row.addStretch(1)
        self.tab_group.idClicked.connect(self.show_tab)
        self.tab_group.button(0).setChecked(True)
        layout.addWidget(self.tab_bar)
        layout.addWidget(self.stack, 1)
        voice.visual.connect(self._on_visual)

    # ----- content -----------------------------------------------------------------------------
    def rows(self) -> list[QRect]:
        """Visible bands from top to bottom (panel coordinates) for the staggered reveal."""
        widgets = [w for w in (self.header, self.music, self.tab_bar, self.stack)
                   if not w.isHidden()]
        return [w.geometry() for w in widgets]

    def show_tab(self, index: int) -> None:
        if index < 0:
            return
        if index != self.stack.currentIndex():
            self.stack.setCurrentIndex(index)
            if self.isVisible():
                motion.fade_in(self.stack.widget(index), motion.FAST_MS)
        button = self.tab_group.button(index)
        if button is not None:
            button.setChecked(True)
        refresh = getattr(self.stack.widget(index), "refresh", None)
        if refresh is not None:
            refresh()

    def open_tab(self, name: str) -> None:
        for index, (tab_name, _widget) in enumerate(self.tabs):
            if tab_name == name:
                self.show_tab(index)

    def refresh_current(self) -> None:
        self.show_tab(self.stack.currentIndex())

    def show_media(self, state) -> None:
        self.music.show_state(state)
        self.music.setVisible(bool(state is not None and state.active))

    def update_key_prompt(self) -> None:
        self.key_prompt.setVisible(not self.has_key())

    def set_accent(self, accent: str) -> None:
        self.orb.set_accent(accent)

    def _on_visual(self, state: str, level: float, text: str) -> None:
        self.orb.set_state(state, level)
        if self.status.text() != text:
            self.status.setText(text)
        self.retry.setVisible(self.voice.live_state == "error")
        self.sync_toggles(self.voice.mic.muted, self.voice.always_listening)

    def sync_toggles(self, muted: bool, always_listening: bool) -> None:
        for box, value in ((self.mute, muted), (self.always, always_listening)):
            if box.isChecked() != value:
                box.blockSignals(True)
                box.setChecked(value)
                box.blockSignals(False)
                box.refresh()
