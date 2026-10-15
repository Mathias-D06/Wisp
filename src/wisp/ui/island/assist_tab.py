"""The island's Screen tab (D-052): Screen Assist's answers and Watch mode.

* A thumbnail of exactly what was sent to Gemini, with the window's name and how many areas
  were hidden (blocklisted windows, Wisp itself).
* Mode chips (Explain, Review, Summarise, Reply) ask again about the same screenshot.
* The conversation, rendered from Markdown (code in a monospace block). Links are never opened:
  an answer can quote text from the screen, and screen text is untrusted.
* More (the detailed version), Copy, Speak / Stop, and for Reply: Insert, which pastes the draft
  into the window the screenshot came from. Nothing is ever sent.
* A follow-up box: the same conversation, the screenshot reused unless the window changed.
* Watch mode: on/off, and what it has done so far.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QPixmap, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from wisp.assist import prompts
from wisp.ui import theme
from wisp.ui.island.common import GlyphButton, glyph_icon

THUMB = QSize(112, 70)


def transcript_markdown(exchanges: list) -> str:
    """The conversation as Markdown: each question in bold, then the answer."""
    blocks = []
    for exchange in exchanges:
        label = exchange.question or "Quick look"
        note = " · new screenshot" if exchange.recaptured else ""
        blocks.append(f"**{escape_markdown(label)}**{note}\n\n{exchange.answer}")
    return "\n\n---\n\n".join(blocks)


def monospace_code(document) -> int:
    """Qt's Markdown import marks fenced code blocks with the generic family "monospace";
    give them Windows' coding fonts. Returns how many blocks were code."""
    fixed = QTextCharFormat()
    fixed.setFontFamilies(theme.FONT_MONO)
    fixed.setFontFixedPitch(True)
    count = 0
    block = document.begin()
    while block.isValid():
        if block.blockFormat().hasProperty(QTextFormat.Property.BlockCodeFence):
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.mergeCharFormat(fixed)
            count += 1
        block = block.next()
    return count


def escape_markdown(text: str) -> str:
    return "".join("\\" + ch if ch in "\\`*_{}[]()#+-.!|<>" else ch for ch in text)


class AssistTab(QWidget):
    def __init__(self, assist, watcher, palette, hotkey_text=lambda: "Ctrl+Alt+Space",
                 clipboard=None):
        super().__init__()
        self.assist = assist
        self.watcher = watcher
        self.hotkey_text = hotkey_text
        self.clipboard = clipboard
        self.exchanges: list = []
        p = palette
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(theme.SPACE["s"])

        header = QHBoxLayout()
        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB)
        self.thumb.setObjectName("Thumb")
        self.thumb.setToolTip("Exactly what was sent to Gemini")
        self.thumb.setScaledContents(False)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.thumb)
        about = QVBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("CardTitle")
        self.title.setWordWrap(True)
        self.detail = QLabel()
        self.detail.setObjectName("Hint")
        self.detail.setWordWrap(True)
        about.addWidget(self.title)
        about.addWidget(self.detail)
        about.addStretch(1)
        header.addLayout(about, 1)
        self.new_look = GlyphButton("look", "Look again (a new screenshot, a new conversation)")
        self.new_look.clicked.connect(lambda: self.assist.ask(new=True, origin="island"))
        header.addWidget(self.new_look)
        layout.addLayout(header)

        chips = QHBoxLayout()
        self.modes = QButtonGroup(self)
        self.mode_buttons: dict[str, QPushButton] = {}
        for index, (name, (label, _instruction)) in enumerate(prompts.MODES.items()):
            button = QPushButton(label)
            button.setObjectName("Tab")
            button.setToolTip(_instruction)
            self.modes.addButton(button, index)
            self.mode_buttons[name] = button
            button.clicked.connect(lambda _c=False, m=name: self.assist.ask(mode=m,
                                                                            origin="island"))
            chips.addWidget(button)
        chips.addStretch(1)
        self.watch_button = QPushButton(glyph_icon("watch", p.secondary), "Watch")
        self.watch_button.setObjectName("Chip")
        self.watch_button.setCheckable(True)
        self.watch_button.setToolTip("Watch mode: Wisp looks at the window in front now and "
                                     "then, and speaks up only when something's wrong")
        self.watch_button.clicked.connect(self._toggle_watch)
        chips.addWidget(self.watch_button)
        layout.addLayout(chips)

        self.view = QTextBrowser()
        self.view.setObjectName("Answer")
        self.view.setOpenLinks(False)
        self.view.setOpenExternalLinks(False)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.view, 1)

        actions = QHBoxLayout()
        self.more_button = QPushButton("More")
        self.more_button.setToolTip("The detailed version of the last answer")
        self.more_button.clicked.connect(self.assist.more)
        self.copy_button = QPushButton(glyph_icon("copy", p.secondary), "Copy")
        self.copy_button.clicked.connect(self._copy)
        self.speak_button = QPushButton(glyph_icon("speaking", p.secondary), "Speak it")
        self.speak_button.clicked.connect(self._speak)
        self.insert_button = QPushButton(glyph_icon("send", p.secondary), "Insert")
        self.insert_button.setToolTip("Paste the draft into the window it's for. Nothing is "
                                      "sent: you check it and send it yourself.")
        self.insert_button.clicked.connect(self._insert)
        for button in (self.more_button, self.copy_button, self.speak_button,
                       self.insert_button):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.follow_up = QLineEdit()
        self.follow_up.setPlaceholderText("Ask a follow-up…")
        self.follow_up.returnPressed.connect(self._ask_follow_up)
        layout.addWidget(self.follow_up)
        self.status = QLabel()
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        assist.answered.connect(self.show_exchange)
        assist.failed.connect(self._failed)
        assist.busy_changed.connect(self._busy)
        assist.speaking_changed.connect(self._speaking)
        watcher.changed.connect(self._watch_changed)
        self._empty()
        self._watch_changed()

    # ----- state ----------------------------------------------------------------------------------
    def _empty(self) -> None:
        self.thumb.clear()
        self.title.setText("Screen Assist")
        self.detail.setText(f"Hold {self.hotkey_text()} over any window and ask a question, or "
                            "just tap it for a quick look. You can also ask by voice: "
                            "“what's on my screen?”")
        self.view.setMarkdown("")
        for button in (self.more_button, self.copy_button, self.speak_button,
                       self.insert_button):
            button.setVisible(False)
        self.follow_up.setEnabled(False)

    def show_exchange(self, exchange) -> None:
        if not exchange.follow_up:
            self.exchanges = []
        self.exchanges.append(exchange)
        shot = exchange.shot
        pixmap = QPixmap()
        pixmap.loadFromData(shot.jpeg, "JPEG")
        self.thumb.setPixmap(pixmap.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        self.title.setText(shot.what[0].upper() + shot.what[1:])
        hidden = (f" · {shot.masked} area{'s' if shot.masked != 1 else ''} hidden"
                  if shot.masked else "")
        self.detail.setText(f"Sent {shot.size[0]}×{shot.size[1]}{hidden}. Images stay in "
                            "memory only.")
        self.view.setMarkdown(transcript_markdown(self.exchanges))
        monospace_code(self.view.document())
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())
        for button in (self.more_button, self.copy_button, self.speak_button):
            button.setVisible(True)
        self.insert_button.setVisible(exchange.mode == "reply")
        self.follow_up.setEnabled(True)
        self.status.setText("")

    def _failed(self, message: str) -> None:
        self.status.setText(message)

    def _busy(self, busy: bool) -> None:
        if busy:
            self.status.setText("Looking…")
        for button in [self.more_button, self.new_look, *self.mode_buttons.values()]:
            button.setEnabled(not busy)

    def _speaking(self, speaking: bool) -> None:
        self.speak_button.setText("Stop" if speaking else "Speak it")

    # ----- actions --------------------------------------------------------------------------------
    def _ask_follow_up(self) -> None:
        text = self.follow_up.text().strip()
        if text and self.assist.ask(text, origin="island"):
            self.follow_up.clear()

    def _last_answer(self) -> str:
        return self.exchanges[-1].answer if self.exchanges else ""

    def _copy(self) -> None:
        board = self.clipboard or QGuiApplication.clipboard()
        board.setText(self._last_answer())
        self.status.setText("Copied.")

    def _speak(self) -> None:
        if self.assist.speaking:
            self.assist.stop_speaking()
        elif self._last_answer():
            self.assist.speak(self._last_answer())

    def _insert(self) -> None:
        self.status.setText(self.assist.insert(self._last_answer()))

    def _toggle_watch(self) -> None:
        self.watcher.toggle()

    def _watch_changed(self) -> None:
        watcher = self.watcher
        self.watch_button.setChecked(watcher.running)
        if watcher.running:
            check = watcher.check
            self.watch_button.setText(f"Watching · {watcher.comments} said")
            self.watch_button.setToolTip(
                f"Watch mode is on: {check.checks} looks, {check.analysed} sent to Gemini "
                f"(the rest hadn't changed). Click to stop.")
        else:
            self.watch_button.setText("Watch")
            if watcher.error:
                self.status.setText(watcher.error)
