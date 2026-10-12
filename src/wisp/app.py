"""Application bootstrap: builds the services, the tray and the windows, and wires them."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QMessageBox

from wisp import paths, startup
from wisp.db import Database
from wisp.keystore import KeyStore
from wisp.logging_setup import configure as configure_logging
from wisp.settings import Settings, SettingsStore
from wisp.single_instance import SingleInstance
from wisp.ui import theme
from wisp.ui.settings.dialog import SettingsDialog
from wisp.ui.settings.general_page import GeneralPage
from wisp.ui.tray import Tray

log = logging.getLogger(__name__)


class WispApp(QObject):
    def __init__(self, qt_app: QApplication, background: bool):
        super().__init__()
        self.qt_app = qt_app
        self.background = background
        self.keystore = KeyStore(paths.secrets_file())
        configure_logging(paths.log_dir(), self.keystore.get)
        log.info("Wisp starting (frozen=%s)", paths.is_frozen())
        self.settings_store = SettingsStore(paths.settings_file())
        self.db = Database(paths.database_file())
        settings = self.settings_store.get()
        self._apply_theme(settings)
        self.tray = Tray(settings.loadout.accent)
        self._settings_dialog: SettingsDialog | None = None
        self.settings_store.subscribe(self._on_settings_changed)

    # ----- lifecycle -------------------------------------------------------------------------
    def start(self) -> None:
        self._build_tray_menu()
        self.tray.show()
        if not self.keystore.has_key():
            self.tray.notify(
                "Wisp is running",
                "Add your Gemini API key in Settings to use voice and AI features.",
            )
            if not self.background:
                self.open_settings("General")

    def quit(self) -> None:
        log.info("Wisp quitting")
        self.tray.hide()
        self.db.close()
        self.qt_app.quit()

    # ----- UI --------------------------------------------------------------------------------
    def _build_tray_menu(self) -> None:
        self.tray.add_action("Settings…", lambda: self.open_settings())
        self.tray.add_separator()
        self.tray.add_action("Quit Wisp", self.quit)
        self.tray.on_click(lambda: self.open_settings())

    def settings_pages(self) -> list:
        return [GeneralPage(self.settings_store, self.keystore)]

    def open_settings(self, page: str | None = None) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.settings_store, self.settings_pages())
        self._settings_dialog.open_page(page)

    def _apply_theme(self, settings: Settings) -> None:
        palette = theme.palette(settings.loadout.theme, settings.loadout.accent)
        self.qt_app.setStyleSheet(theme.stylesheet(palette))

    def _on_settings_changed(self, settings: Settings) -> None:
        self._apply_theme(settings)
        self.tray.set_accent(settings.loadout.accent)
        try:
            if startup.is_enabled() != settings.general.start_with_windows:
                startup.set_enabled(settings.general.start_with_windows)
        except OSError as exc:
            log.error("Could not change start-up setting: %s", exc)
            self.tray.notify("Wisp", f"Could not change the start-up setting: {exc}")


def run(argv: list[str]) -> int:
    instance = SingleInstance()
    qt_app = QApplication(argv)
    qt_app.setApplicationName(paths.APP_NAME)
    qt_app.setQuitOnLastWindowClosed(False)
    if instance.already_running:
        QMessageBox.information(None, "Wisp", "Wisp is already running. Look for it in the tray.")
        return 0
    app = WispApp(qt_app, background="--background" in argv)
    app.start()
    code = qt_app.exec()
    instance.release()
    return code


if __name__ == "__main__":
    sys.exit(run(sys.argv))
