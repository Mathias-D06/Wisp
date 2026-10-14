"""Settings → Accounts: connect Google Calendar with your own OAuth client (D-050)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wisp.gcal import google
from wisp.settings import Settings
from wisp.ui.settings.base import SettingsPage, hint

STEPS = (
    "<ol style='margin-left: -20px'>"
    "<li>Open <a href='https://console.cloud.google.com/'>console.cloud.google.com</a> and "
    "create a project (or pick one).</li>"
    "<li>APIs &amp; Services → Library: enable the <b>Google Calendar API</b>.</li>"
    "<li>Google Auth platform → Branding: give the app a name and your email. Audience: "
    "<b>External</b>, and add your Google account under Test users.</li>"
    "<li>Clients → Create client → <b>Desktop app</b> → Download JSON.</li>"
    "<li>Import that file here, then click Connect and sign in in your browser.</li></ol>"
)
TESTING_NOTE = ("While the app's publishing status is “Testing”, Google ends the sign-in after "
                "7 days; Wisp then asks you to reconnect. See the README for how to avoid it.")


class AccountsPage(SettingsPage):
    title = "Accounts"

    def __init__(self, calendar):
        super().__init__()
        self.calendar = calendar
        layout = QVBoxLayout(self)
        box = QGroupBox("Google Calendar")
        form = QVBoxLayout(box)
        steps = QLabel(STEPS)
        steps.setWordWrap(True)
        steps.setOpenExternalLinks(True)
        form.addWidget(steps)
        form.addWidget(hint(TESTING_NOTE))

        client_row = QHBoxLayout()
        self.client = QLabel()
        self.client.setProperty("secondary", True)
        self.import_button = QPushButton("Import client JSON…")
        self.import_button.clicked.connect(self._import)
        client_row.addWidget(QLabel("OAuth client:"))
        client_row.addWidget(self.client, 1)
        client_row.addWidget(self.import_button)
        form.addLayout(client_row)
        self.client_error = QLabel()
        self.client_error.setProperty("error", True)
        self.client_error.setWordWrap(True)
        form.addWidget(self.client_error)

        self.allow_create = QCheckBox("Let Wisp add events (asks Google for permission to "
                                      "create events on calendars you own)")
        form.addWidget(self.allow_create)
        self.scope_note = hint("Connect again for this to take effect.")
        form.addWidget(self.scope_note)
        self.allow_create.toggled.connect(lambda _on: self.refresh())

        buttons = QHBoxLayout()
        self.connect_button = QPushButton("Connect Google Calendar")
        self.connect_button.setProperty("primary", True)
        self.connect_button.clicked.connect(self._connect)
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setProperty("danger", True)
        self.disconnect_button.clicked.connect(self.calendar.disconnect)
        buttons.addWidget(self.connect_button)
        buttons.addWidget(self.disconnect_button)
        buttons.addStretch(1)
        form.addLayout(buttons)
        self.status = QLabel()
        self.status.setWordWrap(True)
        form.addWidget(self.status)

        self.calendars_box = QWidget()
        self.calendars_layout = QVBoxLayout(self.calendars_box)
        self.calendars_layout.setContentsMargins(0, 0, 0, 0)
        form.addWidget(self.calendars_box)

        island_form = QFormLayout()
        self.heads_up = QSpinBox()
        self.heads_up.setRange(0, 60)
        self.heads_up.setSuffix(" min")
        self.heads_up.setSpecialValueText("Off")
        island_form.addRow("Show the next event in the island", self.heads_up)
        form.addLayout(island_form)
        layout.addWidget(box)
        layout.addStretch(1)
        calendar.changed.connect(self.refresh)

    # ----- settings ----------------------------------------------------------------------------
    def load(self, settings: Settings) -> None:
        self.allow_create.setChecked(settings.calendar.allow_create)
        self.heads_up.setValue(settings.calendar.heads_up_min)
        self.refresh()

    def apply(self, settings: Settings) -> None:
        settings.calendar.allow_create = self.allow_create.isChecked()
        settings.calendar.heads_up_min = self.heads_up.value()

    # ----- actions -----------------------------------------------------------------------------
    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Google OAuth client (Desktop app)",
                                              str(Path.home() / "Downloads"), "JSON (*.json)")
        if path:
            self.import_file(path)

    def import_file(self, path: str) -> None:
        try:
            self.calendar.import_client(Path(path).read_text(encoding="utf-8"))
            self.client_error.clear()
        except (OSError, UnicodeDecodeError, google.CalendarError) as exc:
            self.client_error.setText(str(exc) if isinstance(exc, google.CalendarError)
                                      else f"Couldn't read the file ({exc}).")
        self.refresh()

    def _connect(self) -> None:
        self.calendar.connect_account(self.allow_create.isChecked())
        self.refresh()

    def refresh(self) -> None:
        service = self.calendar
        state = service.state()
        label = service.client_label()
        self.client.setText(label or "not imported yet")
        connected = service.connected
        self.connect_button.setEnabled(service.has_client() and state != "connecting")
        self.connect_button.setText("Reconnect" if state == "reconnect" or (
            connected and self.allow_create.isChecked() != service.can_create())
            else "Connect Google Calendar")
        self.connect_button.setVisible(not connected or state == "reconnect"
                                       or self.allow_create.isChecked() != service.can_create())
        self.disconnect_button.setVisible(connected)
        self.scope_note.setVisible(connected and self.allow_create.isChecked()
                                   != service.can_create())
        calendars = service.store.calendars()
        texts = {
            "disconnected": "Not connected.",
            "connecting": "Waiting for you to sign in to Google in your browser…",
            "reconnect": service.error or "Google sign-in expired: reconnect.",
            "syncing": "Connected · syncing…",
            "error": f"Connected · {service.error}",
            "connected": f"Connected · {len(calendars)} calendar"
                         f"{'' if len(calendars) == 1 else 's'}"
                         + (" · can add events" if service.can_create() else " · read-only"),
        }
        self.status.setText(texts[state])
        self.status.setProperty("error", state in ("reconnect", "error"))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self._fill_calendars(calendars)

    def _fill_calendars(self, calendars: list[dict]) -> None:
        while self.calendars_layout.count():
            item = self.calendars_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        if not calendars:
            return
        self.calendars_layout.addWidget(QLabel("Calendars to show:"))
        for calendar in calendars:
            box = QCheckBox(calendar["title"] + ("  (main)" if calendar["is_primary"] else ""))
            box.setChecked(bool(calendar["shown"]))
            box.setStyleSheet(f"QCheckBox {{ border-left: 4px solid {calendar['color']}; "
                              "padding-left: 6px; }}" if calendar["color"] else "")
            box.toggled.connect(lambda on, cid=calendar["id"]: self._show(cid, on))
            self.calendars_layout.addWidget(box)

    def _show(self, calendar_id: str, shown: bool) -> None:
        self.calendar.store.set_shown(calendar_id, shown)
        self.calendar.changed.emit()
