"""Power tab: lock, sleep, restart, shut down — sleep/restart/shut down ask first."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from wisp.system import power
from wisp.ui.island.common import LOCK, NIGHT, POWER, RESTART, glyph_icon

ACTIONS = [
    ("lock", "Lock", LOCK, None),
    ("sleep", "Sleep", NIGHT, "Put the PC to sleep now?"),
    ("restart", "Restart", RESTART, "Restart now? Unsaved work in other apps may be lost."),
    ("shutdown", "Shut down", POWER, "Shut down now? Unsaved work in other apps may be lost."),
]


class PowerTab(QWidget):
    def __init__(self, background, palette, action_log=None, confirm=None):
        super().__init__()
        self.bg = background
        self.action_log = action_log
        self.confirm = confirm or self._ask
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        grid = QGridLayout()
        self.buttons: dict[str, QPushButton] = {}
        for index, (key, label, glyph, _question) in enumerate(ACTIONS):
            button = QPushButton(glyph_icon(glyph, palette.text, 22), label)
            button.setObjectName("Chip")
            button.setMinimumHeight(64)
            button.clicked.connect(lambda _c=False, k=key: self.trigger(k))
            grid.addWidget(button, index // 2, index % 2)
            self.buttons[key] = button
        layout.addLayout(grid)
        self.status = QLabel()
        self.status.setObjectName("Hint")
        layout.addWidget(self.status)
        layout.addStretch(1)

    def _ask(self, question: str) -> bool:
        return QMessageBox.question(self, "Wisp", question) == QMessageBox.StandardButton.Yes

    def trigger(self, key: str) -> None:
        _, label, _glyph, question = next(a for a in ACTIONS if a[0] == key)
        if question and not self.confirm(question):
            return
        if self.action_log is not None:
            self.action_log.record(origin="ui", tool="power", args={"action": key},
                                   decision="allow (clicked + confirmed)" if question else
                                   "allow (clicked)", result={"ok": True}, ok=True)
        function = {"lock": power.lock, "sleep": power.sleep, "restart": power.restart,
                    "shutdown": power.shutdown}[key]
        self.bg.run(function, None, lambda exc: self.status.setText(f"{label} failed: {exc}"))
