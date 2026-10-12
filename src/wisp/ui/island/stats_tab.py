"""Stats tab (F10): words dictated, time saved, commands, routines — today and this week."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from wisp.ui.island.common import BarChart, section


def format_duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


class StatCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("Card")
        layout = QGridLayout(self)
        heading = QLabel(title)
        heading.setObjectName("CardTitle")
        layout.addWidget(heading, 0, 0, 1, 2)
        self.values: dict[str, QLabel] = {}
        for row, (key, label) in enumerate((("words", "Words dictated"),
                                            ("saved", "Time saved"),
                                            ("commands", "Commands run"),
                                            ("routines", "Routines run")), start=1):
            name = QLabel(label)
            name.setObjectName("Hint")
            value = QLabel("0")
            value.setObjectName("Big")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(name, row, 0)
            layout.addWidget(value, row, 1)
            self.values[key] = value

    def show_summary(self, summary) -> None:
        self.values["words"].setText(f"{summary.words:,}")
        self.values["saved"].setText(format_duration(summary.seconds_saved))
        self.values["commands"].setText(str(summary.commands))
        self.values["routines"].setText(str(summary.routines))


class StatsTab(QWidget):
    _changed = Signal()

    def __init__(self, stats, settings, accent: str):
        super().__init__()
        self.stats = stats
        self.settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        cards = QGridLayout()
        self.today = StatCard("Today")
        self.week = StatCard("This week")
        cards.addWidget(self.today, 0, 0)
        cards.addWidget(self.week, 0, 1)
        layout.addLayout(cards)
        layout.addWidget(section("Last 7 days"))
        self.metric = QComboBox()
        self.metric.addItem("Words dictated", "words")
        self.metric.addItem("Commands run", "commands")
        self.metric.currentIndexChanged.connect(lambda _i: self.refresh())
        layout.addWidget(self.metric)
        self.chart = BarChart(accent)
        layout.addWidget(self.chart, 1)
        self.note = QLabel()
        self.note.setObjectName("Hint")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self._changed.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        stats.subscribe(self._changed.emit)

    def refresh(self) -> None:
        self.today.show_summary(self.stats.today())
        self.week.show_summary(self.stats.this_week())
        key = self.metric.currentData()
        self.chart.set_values([(day.label, getattr(day, key)) for day in self.stats.daily(7)])
        wpm = self.settings.peek().general.typing_wpm
        self.note.setText(f"Time saved = typing time at {wpm} words per minute minus the time you "
                          "spent speaking (change your typing speed in Settings → General).")
