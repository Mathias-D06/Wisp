"""The Island window: a pill fixed at the top centre, always on top, that expands on hover or
scroll into tabs (Controls, Today, Stats, Clipboard, Apps, Wallpaper, Power) with a music strip.
Everything here works without an API key; voice features show an "add your key" prompt.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wisp.ui.island.common import SETTINGS, GlyphButton
from wisp.ui.island.music import MusicStrip
from wisp.ui.orb import Orb

COLLAPSED = (340, 56)
EXPANDED = (680, 560)
MARGIN = 10  # room for the drop shadow


def island_stylesheet(p) -> str:
    surface = QColor(p.surface)
    rgba = f"rgba({surface.red()}, {surface.green()}, {surface.blue()}, 245)"
    return f"""
    #IslandShell {{ background: {rgba}; border: 1px solid {p.border}; border-radius: 20px; }}
    #IslandShell QLabel {{ background: transparent; }}
    QLabel#Status {{ font-size: 10pt; }}
    QLabel#Section {{ color: {p.muted}; font-size: 8pt; letter-spacing: 1px; margin-top: 6px; }}
    QLabel#Hint {{ color: {p.muted}; font-size: 9pt; }}
    QLabel#CardTitle {{ font-weight: 600; }}
    QLabel#Big {{ font-size: 13pt; font-weight: 600; }}
    QFrame#Card {{ background: {p.surface2}; border-radius: 12px; }}
    QPushButton#Tab {{ background: transparent; border: none; color: {p.muted};
        padding: 6px 10px; border-radius: 8px; }}
    QPushButton#Tab:checked {{ background: {p.surface2}; color: {p.text}; }}
    QPushButton#Tab:hover {{ color: {p.text}; }}
    QPushButton#Chip {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 12px;
        padding: 8px 12px; text-align: left; }}
    QPushButton#Chip:checked {{ background: {p.accent}; color: {p.accent_text}; border: none; }}
    QPushButton#Chip:disabled {{ color: {p.muted}; }}
    QPushButton#Glyph {{ background: transparent; border: none; border-radius: 17px; }}
    QPushButton#Glyph:hover {{ background: {p.surface2}; }}
    QPushButton#Glyph:checked {{ color: {p.accent}; }}
    QPushButton#KeyPrompt {{ background: {p.accent}; color: {p.accent_text}; border: none;
        border-radius: 12px; padding: 4px 10px; }}
    QListWidget#Flat {{ background: transparent; border: none; }}
    QListWidget#Flat::item {{ padding: 6px; border-radius: 8px; }}
    QListWidget#Flat::item:hover {{ background: {p.surface2}; }}
    QProgressBar#Thin {{ background: {p.border}; border: none; border-radius: 2px; }}
    QProgressBar#Thin::chunk {{ background: {p.accent}; border-radius: 2px; }}
    """


class Island(QWidget):
    settings_requested = Signal(str)

    def __init__(self, voice, palette, accent: str, has_key, media_command, tabs: list):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Wisp Island")
        self.voice = voice
        self.has_key = has_key
        self.expanded = False
        self.media_state = None
        self._voice_text = "Ready"
        self._voice_state = "idle"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        self.shell = QFrame()
        self.shell.setObjectName("IslandShell")
        shadow = QGraphicsDropShadowEffect(self.shell)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 110))
        self.shell.setGraphicsEffect(shadow)
        outer.addWidget(self.shell)
        layout = QVBoxLayout(self.shell)
        layout.setContentsMargins(12, 6, 12, 10)

        bar = QHBoxLayout()
        self.orb = Orb(26, accent)
        self.orb.clicked.connect(voice.toggle_talk)
        self.status = QLabel("Ready")
        self.status.setObjectName("Status")
        self.key_prompt = QPushButton("Add your API key")
        self.key_prompt.setObjectName("KeyPrompt")
        self.key_prompt.clicked.connect(lambda: self.settings_requested.emit("General"))
        self.settings_button = GlyphButton(SETTINGS, "Settings", 30)
        self.settings_button.clicked.connect(lambda: self.settings_requested.emit(""))
        bar.addWidget(self.orb)
        bar.addWidget(self.status, 1)
        bar.addWidget(self.key_prompt)
        bar.addWidget(self.settings_button)
        layout.addLayout(bar)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 6, 0, 0)
        self.music = MusicStrip(media_command)
        body.addWidget(self.music)
        tab_row = QHBoxLayout()
        self.tab_group = QButtonGroup(self)
        self.stack = QStackedWidget()
        self.tabs = tabs
        for index, (name, widget) in enumerate(tabs):
            button = QPushButton(name)
            button.setObjectName("Tab")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tab_group.addButton(button, index)
            tab_row.addWidget(button)
            self.stack.addWidget(widget)
        tab_row.addStretch(1)
        self.tab_group.idClicked.connect(self.show_tab)
        body.addLayout(tab_row)
        body.addWidget(self.stack, 1)
        layout.addWidget(self.body)

        self._expand_timer = QTimer(self, singleShot=True, interval=140)
        self._expand_timer.timeout.connect(self.expand)
        self._collapse_timer = QTimer(self, singleShot=True, interval=650)
        self._collapse_timer.timeout.connect(self._maybe_collapse)
        voice.visual.connect(self._on_visual)
        self.set_palette(palette)
        self.collapse()
        if tabs:
            self.tab_group.button(0).setChecked(True)

    # ----- appearance --------------------------------------------------------------------------
    def set_palette(self, palette) -> None:
        self.setStyleSheet(island_stylesheet(palette))

    def set_accent(self, accent: str) -> None:
        self.orb.set_accent(accent)

    def _place(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(QPoint(screen.x() + (screen.width() - self.width()) // 2,
                         screen.y() + 2 - MARGIN // 2))

    def update_key_prompt(self) -> None:
        self.key_prompt.setVisible(not self.has_key())
        self._refresh_status()

    # ----- expand / collapse -------------------------------------------------------------------
    def expand(self) -> None:
        if self.expanded:
            return
        self.expanded = True
        self.body.setVisible(True)
        self.settings_button.setVisible(True)
        self.setFixedSize(EXPANDED[0] + 2 * MARGIN, EXPANDED[1] + 2 * MARGIN)
        self._place()
        self.show_tab(self.stack.currentIndex())

    def collapse(self) -> None:
        self.expanded = False
        self.body.setVisible(False)
        self.settings_button.setVisible(False)
        self.setFixedSize(COLLAPSED[0] + 2 * MARGIN, COLLAPSED[1] + 2 * MARGIN)
        self._place()

    def _maybe_collapse(self) -> None:
        if self.geometry().contains(QCursor.pos()):
            return
        if QApplication.activePopupWidget() is not None or QApplication.activeModalWidget():
            self._collapse_timer.start()
            return
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit) and self.isAncestorOf(focus) and focus.text():
            self._collapse_timer.start()
            return
        self.collapse()

    def enterEvent(self, event) -> None:
        self._collapse_timer.stop()
        self._expand_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._expand_timer.stop()
        self._collapse_timer.start()
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:
        self.expand()
        super().wheelEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate and self.expanded:
            self._collapse_timer.start()
        return super().event(event)

    def show_tab(self, index: int) -> None:
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        button = self.tab_group.button(index)
        if button is not None:
            button.setChecked(True)
        widget = self.stack.widget(index)
        refresh = getattr(widget, "refresh", None)
        if refresh is not None:
            refresh()

    def open_tab(self, name: str) -> None:
        for index, (tab_name, _widget) in enumerate(self.tabs):
            if tab_name == name:
                self.expand()
                self.show_tab(index)

    # ----- status ------------------------------------------------------------------------------
    def _on_visual(self, state: str, level: float, text: str) -> None:
        self.orb.set_state(state, level)
        self._voice_state, self._voice_text = state, text
        self._refresh_status()

    def show_media(self, state) -> None:
        self.media_state = state
        self.music.show_state(state)
        self._refresh_status()

    def _refresh_status(self) -> None:
        media = self.media_state
        if self._voice_state == "idle" and media is not None and media.active and media.playing:
            text = f"♪ {media.title}" + (f" — {media.artist}" if media.artist else "")
        elif not self.has_key() and self._voice_state in ("idle", "offline"):
            text = "Island ready · voice needs a key"
        else:
            text = self._voice_text
        metrics = self.status.fontMetrics()
        self.status.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight,
                                               max(80, self.status.width())))
        self.status.setToolTip(text)
