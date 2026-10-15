"""Settings → Discreet mode (D-053): its own profile, separate from the normal settings."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
)

from wisp.settings import Settings
from wisp.ui.settings.base import SettingsPage, hint


class DiscreetPage(SettingsPage):
    title = "Discreet mode"

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(hint("For lectures, libraries and meetings: Wisp keeps working but is "
                              "much less noticeable. These settings only apply while Discreet "
                              "mode is on; turning it off brings back your normal Wisp exactly "
                              "as before. Turn it on here, from the Island's or the tray's menu, "
                              "with Ctrl+Alt+D, or say “go discreet”. Wisp's windows stay normal "
                              "windows: screen sharing and recording still show them."))
        self.enabled = QCheckBox("Discreet mode is on")
        layout.addWidget(self.enabled)

        island = QGroupBox("The Island")
        form = QFormLayout(island)
        self.style = QComboBox()
        self.style.addItem("A thin line", "line")
        self.style.addItem("A small dot", "dot")
        self.position = QComboBox()
        self.position.addItem("Top centre", "top-centre")
        self.position.addItem("Top left corner", "top-left")
        self.position.addItem("Top right corner", "top-right")
        self.opacity = QSpinBox()
        self.opacity.setRange(20, 100)
        self.opacity.setSuffix(" %")
        form.addRow("Shape", self.style)
        form.addRow("Where", self.position)
        form.addRow("Opacity", self.opacity)
        form.addRow(hint("Grey, no glow or animation. It still slides away when nothing is "
                         "happening and comes back from the top edge above it. Watch mode and "
                         "the phone link always show a small coloured dot."))
        layout.addWidget(island)

        answers = QGroupBox("Answers and notifications")
        answer_form = QFormLayout(answers)
        self.card_seconds = QSpinBox()
        self.card_seconds.setRange(3, 120)
        self.card_seconds.setSuffix(" s")
        self.card_text = QSpinBox()
        self.card_text.setRange(11, 20)
        self.card_text.setSuffix(" px")
        self.card_opacity = QSpinBox()
        self.card_opacity.setRange(85, 100)
        self.card_opacity.setSuffix(" %")
        self.speak = QCheckBox("Keep spoken replies (with headphones)")
        self.mute_toasts = QCheckBox("No Windows notifications either")
        answer_form.addRow("Answer card fades after", self.card_seconds)
        answer_form.addRow("Card text size", self.card_text)
        answer_form.addRow("Card background", self.card_opacity)
        answer_form.addRow("", self.speak)
        answer_form.addRow("", self.mute_toasts)
        answer_form.addRow(hint("Replies appear as quiet text under the Island instead of being "
                                "spoken (“Speak it” on the card reads one aloud). Notifications "
                                "become a short pulse of the line; only errors and "
                                "confirmations open up. Always listening pauses: hold the talk "
                                "key."))
        layout.addWidget(answers)

        schedule = QGroupBox("Schedule")
        schedule_form = QVBoxLayout(schedule)
        self.during_events = QCheckBox("Turn on by itself during Google Calendar events")
        schedule_form.addWidget(self.during_events)
        schedule_form.addWidget(hint("Timed events on the calendars you show (Settings → "
                                     "Accounts). It turns off when the event ends; if you turn "
                                     "it off during an event it stays off until that event "
                                     "ends."))
        layout.addWidget(schedule)
        layout.addStretch(1)

    def load(self, settings: Settings) -> None:
        d = settings.discreet
        self.enabled.setChecked(d.enabled)
        self.style.setCurrentIndex(max(0, self.style.findData(d.style)))
        self.position.setCurrentIndex(max(0, self.position.findData(d.position)))
        self.opacity.setValue(d.opacity)
        self.card_seconds.setValue(d.card_seconds)
        self.card_text.setValue(d.card_text_px)
        self.card_opacity.setValue(d.card_opacity)
        self.speak.setChecked(d.speak_replies)
        self.mute_toasts.setChecked(d.mute_toasts)
        self.during_events.setChecked(d.during_events)

    def apply(self, settings: Settings) -> None:
        d = settings.discreet
        d.enabled = self.enabled.isChecked()
        d.style = self.style.currentData()
        d.position = self.position.currentData()
        d.opacity = self.opacity.value()
        d.card_seconds = self.card_seconds.value()
        d.card_text_px = self.card_text.value()
        d.card_opacity = self.card_opacity.value()
        d.speak_replies = self.speak.isChecked()
        d.mute_toasts = self.mute_toasts.isChecked()
        d.during_events = self.during_events.isChecked()
