"""The Settings window: a tab per page, OK/Apply/Cancel."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
)

from wisp.settings import SettingsStore
from wisp.ui.settings.base import SettingsPage

log = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    def __init__(self, store: SettingsStore, pages: list[SettingsPage], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wisp settings")
        self.setMinimumSize(760, 600)
        self._store = store
        self._pages = pages
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        for page in pages:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, page.title)
        layout.addWidget(self.tabs)
        self.error = QLabel()
        self.error.setProperty("error", True)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        layout.addWidget(buttons)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

    def open_page(self, title: str | None = None) -> None:
        settings = self._store.get()
        for page in self._pages:
            page.load(settings)
        if title:
            for index, page in enumerate(self._pages):
                if page.title == title:
                    self.tabs.setCurrentIndex(index)
        self.error.clear()
        self.show()
        self.raise_()
        self.activateWindow()

    def apply(self) -> bool:
        settings = self._store.get()
        try:
            for page in self._pages:
                page.apply(settings)
            self._store.save(settings)
        except ValueError as exc:
            self.error.setText(str(exc))
            return False
        except OSError as exc:
            log.exception("Saving settings failed")
            self.error.setText(f"Could not save settings: {exc}")
            return False
        self.error.clear()
        return True

    def _ok(self) -> None:
        if self.apply():
            self.accept()
