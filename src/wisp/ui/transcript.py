"""Transcript as message rows (console): a subtle "You"/"Wisp" label over the text, system notes
in small muted type with an icon, new rows fading in, and the view following the newest row
unless the user has scrolled up."""

from __future__ import annotations

import html

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from wisp.ui import iconset, motion, theme

LABELS = {"user": "You", "model": "Wisp"}


def body_html(text: str, color: str) -> str:
    escaped = html.escape(text).replace("\n", "<br>")
    return (f'<div style="line-height:{int(theme.LINE_HEIGHT * 100)}%; color:{color};">'
            f"{escaped}</div>")


class MessageRow(QFrame):
    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        self.role = role
        self.setObjectName("MessageRow")
        layout = QHBoxLayout(self) if role == "notice" else QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4 if role != "notice" else theme.SPACE["s"])
        self.icon = None
        if role == "notice":
            self.icon = QLabel()
            self.icon.setFixedSize(QSize(theme.ICON_SM, theme.ICON_SM))
            layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        else:
            self.label = QLabel(LABELS[role])
            self.label.setProperty("caption", True)
            self.label.setProperty("secondary", True)
            layout.addWidget(self.label)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if role == "notice":
            self.body.setProperty("caption", True)
        layout.addWidget(self.body, 1)
        self.text, self.final = "", True

    def set_text(self, text: str, final: bool) -> None:
        self.text, self.final = text, final
        p = theme.current()
        color = p.muted if self.role == "notice" else (p.text if final else p.secondary)
        self.body.setText(body_html(text + ("" if final else " …"), color))
        if self.icon is not None:
            pixmap = iconset.icon("info", p.muted).pixmap(QSize(theme.ICON_SM, theme.ICON_SM),
                                                          self.devicePixelRatioF())
            self.icon.setPixmap(pixmap)


class TranscriptView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Transcript")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._content.setObjectName("TranscriptContent")
        self._rows = QVBoxLayout(self._content)
        self._rows.setContentsMargins(theme.SPACE["m"], theme.SPACE["m"], theme.SPACE["m"],
                                      theme.SPACE["m"])
        self._rows.setSpacing(theme.SPACE["m"])
        self._rows.addStretch(1)
        self.setWidget(self._content)
        theme.signals.changed.connect(self.restyle)

    def rows(self) -> list[MessageRow]:
        return [self._rows.itemAt(i).widget() for i in range(self._rows.count() - 1)]

    def add_row(self, role: str, text: str, final: bool) -> MessageRow:
        follow = self._at_bottom()
        row = MessageRow(role, self._content)
        row.set_text(text, final)
        self._rows.insertWidget(self._rows.count() - 1, row)
        motion.fade_in(row)
        if follow:
            self._follow()
        return row

    def update_row(self, row: MessageRow, text: str, final: bool) -> None:
        follow = self._at_bottom()
        row.set_text(text, final)
        if follow:
            self._follow()

    def trim(self, keep: int) -> None:
        rows = self.rows()
        for row in rows[:max(0, len(rows) - keep)]:
            self._rows.removeWidget(row)
            row.deleteLater()

    def restyle(self, _palette=None) -> None:
        for row in self.rows():
            row.set_text(row.text, row.final)

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 24

    def _follow(self) -> None:
        # The view is the context: if it is deleted first, Qt drops the call.
        QTimer.singleShot(0, self, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()))
