"""Settings → Screen Assist (D-052): answers, Watch mode and the windows Wisp never looks at."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from wisp.assist.privacy import DEFAULT_APPS, DEFAULT_TITLES
from wisp.settings import Settings
from wisp.ui.settings.base import SettingsPage, hint


def lines(edit: QPlainTextEdit) -> list[str]:
    seen, result = set(), []
    for line in edit.toPlainText().splitlines():
        item = line.strip()
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return result


class AssistPage(SettingsPage):
    title = "Screen Assist"

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(hint("Hold the Screen Assist hotkey (Settings → Hotkeys and audio) over "
                              "a window and ask, or tap it for a quick look. Screenshots stay in "
                              "memory for the current question and are never saved, unless the "
                              "troubleshooting option on Hotkeys and audio is on. Every capture "
                              "is listed in the Action log (without the image)."))

        answers = QGroupBox("Answers")
        form = QFormLayout(answers)
        self.capture = QComboBox()
        self.capture.addItem("The window in front", "window")
        self.capture.addItem("The whole screen it's on", "screen")
        form.addRow("Look at", self.capture)
        self.speak = QCheckBox("Read answers aloud")
        form.addRow("", self.speak)
        layout.addWidget(answers)

        watch = QGroupBox("Watch mode (off until you turn it on)")
        watch_form = QFormLayout(watch)
        self.interval = QSpinBox()
        self.interval.setRange(10, 600)
        self.interval.setSuffix(" s")
        self.gap = QSpinBox()
        self.gap.setRange(15, 3600)
        self.gap.setSuffix(" s")
        self.auto_stop = QSpinBox()
        self.auto_stop.setRange(1, 480)
        self.auto_stop.setSuffix(" min")
        self.watch_speak = QCheckBox("Read Watch comments aloud")
        watch_form.addRow("Look every", self.interval)
        watch_form.addRow("Speak up at most every", self.gap)
        watch_form.addRow("Stop by itself after", self.auto_stop)
        watch_form.addRow("", self.watch_speak)
        watch_form.addRow(hint("A look is only sent to Gemini when the window has changed "
                               "noticeably. Stats shows how many looks were sent and an "
                               "estimate of the cost."))
        layout.addWidget(watch)

        never = QGroupBox("Never look at")
        grid = QGridLayout(never)
        grid.addWidget(QLabel("Apps (one per line)"), 0, 0)
        grid.addWidget(QLabel("Window titles containing (one per line)"), 0, 1)
        self.apps = QPlainTextEdit()
        self.titles = QPlainTextEdit()
        for edit in (self.apps, self.titles):
            edit.setMinimumHeight(140)
        grid.addWidget(self.apps, 1, 0)
        grid.addWidget(self.titles, 1, 1)
        row = QHBoxLayout()
        restore = QPushButton("Restore defaults")
        restore.clicked.connect(self._defaults)
        row.addWidget(restore)
        row.addStretch(1)
        grid.addLayout(row, 2, 0, 1, 2)
        grid.addWidget(hint("Apps are matched by program name (as in Task Manager's Details "
                            "tab, without .exe). Title words match whole words, any case; a "
                            "browser is skipped while such a page is in front. Private browsing "
                            "windows are recognised by their titles (Incognito, InPrivate, "
                            "Private Browsing). On a whole-screen look these windows are painted "
                            "over. Wisp says “I don't look at that window” instead."), 3, 0, 1, 2)
        layout.addWidget(never)
        layout.addStretch(1)

    def _defaults(self) -> None:
        self.apps.setPlainText("\n".join(DEFAULT_APPS))
        self.titles.setPlainText("\n".join(DEFAULT_TITLES))

    def load(self, settings: Settings) -> None:
        assist = settings.screen_assist
        self.capture.setCurrentIndex(max(0, self.capture.findData(assist.capture)))
        self.speak.setChecked(assist.speak_answers)
        self.interval.setValue(assist.watch_interval_s)
        self.gap.setValue(assist.watch_comment_gap_s)
        self.auto_stop.setValue(assist.watch_auto_stop_min)
        self.watch_speak.setChecked(assist.watch_speak)
        self.apps.setPlainText("\n".join(assist.blocked_apps))
        self.titles.setPlainText("\n".join(assist.blocked_titles))

    def apply(self, settings: Settings) -> None:
        assist = settings.screen_assist
        assist.capture = self.capture.currentData()
        assist.speak_answers = self.speak.isChecked()
        assist.watch_interval_s = self.interval.value()
        assist.watch_comment_gap_s = self.gap.value()
        assist.watch_auto_stop_min = self.auto_stop.value()
        assist.watch_speak = self.watch_speak.isChecked()
        assist.blocked_apps = lines(self.apps)
        assist.blocked_titles = lines(self.titles)
