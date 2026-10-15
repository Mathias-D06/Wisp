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


def usage_text(usage: dict, prices_checked: str) -> str:
    """Today's Gemini use by Screen Assist, Watch mode and reading aloud (D-052)."""
    if not usage:
        return "No Screen Assist or Watch mode use today."
    parts = []
    if "screen_assist" in usage:
        n = usage["screen_assist"].requests
        parts.append(f"Screen Assist: {n} answer{'s' if n != 1 else ''}")
    if "watch" in usage:
        watch = usage["watch"]
        parts.append(f"Watch mode: {watch.requests + watch.skipped} looks, {watch.requests} "
                     f"sent ({watch.skipped} unchanged, skipped)")
    if "speech" in usage:
        parts.append(f"read aloud: {usage['speech'].requests}")
    tokens = sum(u.input_tokens + u.output_tokens for u in usage.values())
    costs = [u.cost for u in usage.values()]
    if any(c is None for c in costs):
        money = "cost unknown for this model"
    else:
        money = f"≈ ${sum(costs):.3f} at Google's prices of {prices_checked}"
    tokens_text = f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)
    return " · ".join(parts) + f" · {tokens_text} tokens · {money}"


class StatsTab(QWidget):
    _changed = Signal()

    def __init__(self, stats, settings, accent: str, usage=None):
        super().__init__()
        self.stats = stats
        self.settings = settings
        self.usage = usage
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        cards = QGridLayout()
        self.today = StatCard("Today")
        self.week = StatCard("This week")
        cards.addWidget(self.today, 0, 0)
        cards.addWidget(self.week, 0, 1)
        layout.addLayout(cards)
        layout.addWidget(section("Last 7 days"))
        self.chart_metric = QComboBox()
        self.chart_metric.addItem("Words dictated", "words")
        self.chart_metric.addItem("Commands run", "commands")
        self.chart_metric.currentIndexChanged.connect(lambda _i: self.refresh())
        layout.addWidget(self.chart_metric)
        self.chart = BarChart(accent)
        layout.addWidget(self.chart, 1)
        self.note = QLabel()
        self.note.setObjectName("Hint")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addWidget(section("Gemini use today"))
        self.usage_label = QLabel()
        self.usage_label.setObjectName("Hint")
        self.usage_label.setWordWrap(True)
        layout.addWidget(self.usage_label)
        self._changed.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        stats.subscribe(self._changed.emit)
        if usage is not None:
            usage.subscribe(self._changed.emit)

    def refresh(self) -> None:
        self.today.show_summary(self.stats.today())
        self.week.show_summary(self.stats.this_week())
        key = self.chart_metric.currentData()
        self.chart.set_values([(day.label, getattr(day, key)) for day in self.stats.daily(7)])
        wpm = self.settings.peek().general.typing_wpm
        self.note.setText(f"Time saved = typing time at {wpm} words per minute minus the time you "
                          "spent speaking (change your typing speed in Settings → General).")
        if self.usage is not None:
            from wisp.stores.usage import PRICES_CHECKED

            self.usage_label.setText(usage_text(self.usage.today(), PRICES_CHECKED))
