"""Calendar tab (D-050): Google Calendar in the island. An agenda of today and the next 7 days
by default, or a compact month view; all-day events on top, each row with its calendar's colour;
a click opens the event in Google Calendar in the browser. Works offline from the cache
("Last synced …") and asks to connect or reconnect when needed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wisp.gcal.times import Event, agenda, day_label, localize, month_grid, span_text
from wisp.ui import theme
from wisp.ui.island.common import section
from wisp.ui.widgets import IconButton

AGENDA_DAYS = 8  # today + the next 7 days


def ago(when: datetime | None, now: datetime) -> str:
    if when is None:
        return "Not synced yet"
    seconds = max(0, int((now - when).total_seconds()))
    if seconds < 60:
        return "Synced just now"
    if seconds < 3600:
        return f"Synced {seconds // 60} min ago"
    if seconds < 86400:
        return f"Last synced {seconds // 3600} h ago"
    return f"Last synced {when:%a %d %b %H:%M}"


class Dot(QWidget):
    """The calendar's colour."""

    def __init__(self, color: str, size: int = 8, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(size + 4, size + 4)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.color or theme.palette_for(self).accent))
        painter.drawEllipse(QRectF(2, 2, self.width() - 4, self.height() - 4))
        painter.end()


class EventRow(QFrame):
    """Time, colour and title; click → the event in Google Calendar."""

    def __init__(self, event: Event, day: date, tz, parent=None):
        super().__init__(parent)
        self.setObjectName("EventRow")
        self.item = event  # not `event`: that would hide QWidget.event()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Open in Google Calendar" + (f" · {event.location}"
                                                     if event.location else ""))
        row = QHBoxLayout(self)
        row.setContentsMargins(theme.SPACE["s"], theme.SPACE["xs"], theme.SPACE["s"],
                               theme.SPACE["xs"])
        row.setSpacing(theme.SPACE["s"])
        row.addWidget(Dot(event.color))
        self.time = QLabel(span_text(event, day, tz))
        self.time.setObjectName("Hint")
        self.time.setFixedWidth(96)
        self.title = QLabel(event.title)
        self.title.setObjectName("CardTitle")
        row.addWidget(self.time)
        row.addWidget(self.title, 1)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.item.link:
            QDesktopServices.openUrl(QUrl(self.item.link))
        super().mouseReleaseEvent(event)


class MonthGrid(QWidget):
    """Six weeks with the day number and up to three colour dots per day."""

    day_clicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.month = date.today().replace(day=1)
        self.today = date.today()
        self.selected = self.today
        self.dots: dict[date, list[str]] = {}
        self.setMinimumHeight(6 * 34 + 22)

    def sizeHint(self) -> QSize:
        return QSize(420, 6 * 34 + 22)

    def cell(self, row: int, column: int) -> QRectF:
        width = self.width() / 7
        height = (self.height() - 22) / 6
        return QRectF(column * width, 22 + row * height, width, height)

    def paintEvent(self, _event) -> None:
        p = theme.palette_for(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(theme.ui_font(theme.CAPTION))
        for column, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            painter.setPen(QColor(p.muted))
            painter.drawText(QRectF(column * self.width() / 7, 0, self.width() / 7, 18),
                             Qt.AlignmentFlag.AlignCenter, name)
        for row, week in enumerate(month_grid(self.month.year, self.month.month)):
            for column, day in enumerate(week):
                box = self.cell(row, column).adjusted(2, 2, -2, -2)
                if day == self.selected:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(p.surface2))
                    painter.drawRoundedRect(box, theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)
                color = p.text if day.month == self.month.month else p.muted
                if day == self.today:
                    color = p.accent
                painter.setPen(QColor(color))
                painter.setFont(theme.ui_font(theme.BODY))
                painter.drawText(box.adjusted(0, 2, 0, -12), Qt.AlignmentFlag.AlignHCenter
                                 | Qt.AlignmentFlag.AlignTop, str(day.day))
                dots = self.dots.get(day, [])[:3]
                for index, dot in enumerate(dots):
                    x = box.center().x() + (index - (len(dots) - 1) / 2) * 7
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(dot or p.accent))
                    painter.drawEllipse(QRectF(x - 2.5, box.bottom() - 8, 5, 5))
        painter.end()

    def mouseReleaseEvent(self, event) -> None:
        for row, week in enumerate(month_grid(self.month.year, self.month.month)):
            for column, day in enumerate(week):
                if self.cell(row, column).contains(event.position()):
                    self.selected = day
                    self.update()
                    self.day_clicked.emit(day)
                    return


class CalendarTab(QWidget):
    open_accounts = Signal()

    def __init__(self, service, now=None):
        super().__init__()
        self.service = service
        self._now = now or (lambda: datetime.now(service.tz()))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(theme.SPACE["s"])

        header = QHBoxLayout()
        self.views = QButtonGroup(self)
        for index, name in enumerate(("Agenda", "Month")):
            button = QPushButton(name)
            button.setObjectName("Tab")
            button.setCheckable(True)
            self.views.addButton(button, index)
            header.addWidget(button)
        self.views.button(0).setChecked(True)
        self.views.idClicked.connect(self._show_view)
        header.addStretch(1)
        self.status = QLabel()
        self.status.setObjectName("Hint")
        self.refresh_button = IconButton("retry", "Sync now")
        self.refresh_button.clicked.connect(self._sync_now)
        header.addWidget(self.status)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        self.prompt = QFrame()
        self.prompt.setObjectName("Card")
        prompt_row = QHBoxLayout(self.prompt)
        self.prompt_text = QLabel()
        self.prompt_text.setWordWrap(True)
        self.prompt_button = QPushButton()
        self.prompt_button.setObjectName("KeyPrompt")
        self.prompt_button.clicked.connect(self.open_accounts)
        prompt_row.addWidget(self.prompt_text, 1)
        prompt_row.addWidget(self.prompt_button)
        layout.addWidget(self.prompt)

        self.stack = QStackedWidget()
        self.agenda_list = QWidget()
        self.agenda_list.setObjectName("ScrollList")  # transparent, like the rest of the panel
        self.agenda_layout = QVBoxLayout(self.agenda_list)
        self.agenda_layout.setContentsMargins(0, 0, 0, 0)
        self.agenda_layout.setSpacing(2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.agenda_list)
        self.stack.addWidget(scroll)

        month_page = QWidget()
        month_layout = QVBoxLayout(month_page)
        month_layout.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        previous = IconButton("previous", "Previous month")
        following = IconButton("next", "Next month")
        self.month_title = QLabel()
        self.month_title.setObjectName("CardTitle")
        previous.clicked.connect(lambda: self._move_month(-1))
        following.clicked.connect(lambda: self._move_month(1))
        nav.addWidget(previous)
        nav.addWidget(self.month_title, 1, Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(following)
        month_layout.addLayout(nav)
        self.grid = MonthGrid()
        self.grid.day_clicked.connect(lambda _day: self._fill_day())
        month_layout.addWidget(self.grid)
        self.day_list = QWidget()
        self.day_layout = QVBoxLayout(self.day_list)
        self.day_layout.setContentsMargins(0, 0, 0, 0)
        self.day_layout.setSpacing(2)
        month_layout.addWidget(self.day_list, 1)
        self.stack.addWidget(month_page)
        layout.addWidget(self.stack, 1)
        service.changed.connect(self._changed)

    # ----- data ----------------------------------------------------------------------------------
    def refresh(self) -> None:
        """The tab came into view: sync if the cache is stale, then show what's cached."""
        self.service.tab_opened()
        self.rebuild()

    def _changed(self) -> None:
        if self.isVisible():
            self.rebuild()

    def _sync_now(self) -> None:
        if not self.service.sync_now():
            self.rebuild()

    def rebuild(self) -> None:
        self._update_status()
        if self.views.checkedId() == 1:
            self._fill_month()
        else:
            self._fill_agenda()

    def _update_status(self) -> None:
        service = self.service
        state = service.state()
        now = self._now()
        self.prompt.setVisible(state in ("disconnected", "reconnect", "connecting"))
        if state == "disconnected":
            self.prompt_text.setText("See your Google Calendar here and ask Wisp what's on.")
            self.prompt_button.setText("Connect Google Calendar")
        elif state == "reconnect":
            self.prompt_text.setText(service.error or "Google sign-in expired.")
            self.prompt_button.setText("Reconnect")
        elif state == "connecting":
            self.prompt_text.setText("Finish signing in to Google in your browser…")
            self.prompt_button.setText("Settings")
        status = "Syncing…" if state == "syncing" else ago(service.store.last_synced(), now)
        if state == "error":
            status = f"Offline · {ago(service.store.last_synced(), now).lower()}"
            self.status.setToolTip(service.error)
        else:
            self.status.setToolTip("")
        self.status.setText(status if service.connected else "")
        self.refresh_button.setVisible(service.connected)

    def _events(self, first: date, days: int) -> list[Event]:
        tz = self.service.tz()
        start = localize(datetime.combine(first, datetime.min.time()), tz)
        end = localize(datetime.combine(first + timedelta(days=days), datetime.min.time()), tz)
        return self.service.events(start, end)

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()  # gone from the next paint, not only once deleted
                item.widget().deleteLater()

    def _fill_agenda(self) -> None:
        self._clear(self.agenda_layout)
        tz = self.service.tz()
        today = self._now().date()
        grouped = agenda(self._events(today, AGENDA_DAYS), today, AGENDA_DAYS, tz)
        for day, events in grouped:
            self.agenda_layout.addWidget(section(day_label(day, today)))
            for event in events:
                self.agenda_layout.addWidget(EventRow(event, day, tz))
        if not grouped and self.service.connected:
            empty = QLabel("Nothing in the next 7 days.")
            empty.setObjectName("Hint")
            self.agenda_layout.addWidget(empty)
        self.agenda_layout.addStretch(1)

    def _fill_month(self) -> None:
        tz = self.service.tz()
        self.grid.today = self._now().date()
        weeks = month_grid(self.grid.month.year, self.grid.month.month)
        first, last = weeks[0][0], weeks[-1][-1]
        dots: dict[date, list[str]] = {}
        for day, events in agenda(self._events(first, (last - first).days + 1), first,
                                  (last - first).days + 1, tz):
            dots[day] = [event.color for event in events]
        self.grid.dots = dots
        self.month_title.setText(f"{self.grid.month:%B %Y}")
        self.grid.update()
        self._fill_day()

    def _fill_day(self) -> None:
        self._clear(self.day_layout)
        tz = self.service.tz()
        day = self.grid.selected
        grouped = agenda(self._events(day, 1), day, 1, tz)
        self.day_layout.addWidget(section(day_label(day, self._now().date())))
        for _day, events in grouped:
            for event in events:
                self.day_layout.addWidget(EventRow(event, day, tz))
        if not grouped:
            empty = QLabel("No events.")
            empty.setObjectName("Hint")
            self.day_layout.addWidget(empty)
        self.day_layout.addStretch(1)

    def _show_view(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.rebuild()

    def _move_month(self, step: int) -> None:
        month = self.grid.month
        index = month.month - 1 + step
        self.grid.month = date(month.year + index // 12, index % 12 + 1, 1)
        self._fill_month()
