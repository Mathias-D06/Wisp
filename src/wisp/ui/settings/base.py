"""Common pieces for settings pages."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from wisp.settings import Settings


class SettingsPage(QWidget):
    """A tab in the Settings window.

    Pages that edit :class:`Settings` implement ``load``/``apply``; pages that manage stored data
    (memories, tasks, action log) act on their stores directly and keep the defaults.
    """

    title = "Page"
    reload_after_apply = False
    """Reload from the saved settings after Apply (for values another page may change)."""

    def load(self, settings: Settings) -> None:
        """Fill widgets from ``settings``. Data-only pages refresh their lists instead."""
        self.refresh()

    def apply(self, settings: Settings) -> None:
        """Copy widget values into ``settings``. Data-only pages have nothing to copy."""

    def refresh(self) -> None:
        """Reload any data shown on the page. Pages with live data override this."""


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("muted", True)
    return label
