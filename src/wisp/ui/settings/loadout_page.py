"""Settings → Loadout: the four slots that shape Wisp — voice, personality, appearance, skills
(F9, DECISIONS.md D-033)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from wisp.live.config import PERSONALITIES
from wisp.settings import (
    CUSTOM_PERSONALITY_MAX,
    PERSONALITY_PRESETS,
    THEMES,
    TOOL_GROUPS,
    VOICES,
    Settings,
)
from wisp.ui.settings.base import SettingsPage, hint
from wisp.ui.theme import ACCENTS

SKILLS = {
    "apps": "Open apps",
    "windows": "Switch, minimise and close windows",
    "web": "Web, YouTube and Amazon searches",
    "screen": "Look at the screen",
    "ui": "Click and type in apps (UI Automation)",
    "files": "Open, find and delete files",
    "todos": "To-dos and reminders",
    "schedule": "Scheduled tasks and routines",
    "memory": "Remember things about you",
    "system": "Volume, brightness, Wi-Fi, Bluetooth, theme",
    "media": "Music and video controls",
    "power": "Lock, sleep, restart, shut down",
    "clipboard": "Clipboard and its history",
    "terminal": "Run terminal commands",
    "input": "Raw mouse and keyboard control",
}
NEEDS_SAFETY = {"terminal": "allow_terminal", "input": "allow_raw_input"}


class LoadoutPage(SettingsPage):
    title = "Loadout"
    reload_after_apply = True  # Settings → Safety can tick the terminal/input skills

    def __init__(self, registry=None):
        super().__init__()
        self.registry = registry
        layout = QVBoxLayout(self)
        layout.addWidget(hint("Your loadout shapes how Wisp sounds, behaves and looks, and which "
                              "skills it may use. Voice, personality and skill changes start a "
                              "fresh voice connection on your next turn; the conversation "
                              "carries on where possible."))

        voice_box = QGroupBox("Voice")
        voice_form = QFormLayout(voice_box)
        self.voice = QComboBox()
        self.voice.addItems(VOICES)
        voice_form.addRow("Gemini voice", self.voice)
        layout.addWidget(voice_box)

        personality_box = QGroupBox("Personality")
        personality_layout = QVBoxLayout(personality_box)
        self.personality = QComboBox()
        for preset in PERSONALITY_PRESETS:
            label = preset.capitalize()
            if PERSONALITIES.get(preset):
                label += f" — {PERSONALITIES[preset]}"
            self.personality.addItem(label, preset)
        self.personality.currentIndexChanged.connect(self._sync_custom)
        self.custom = QPlainTextEdit()
        self.custom.setPlaceholderText("Describe how Wisp should talk, e.g. “a dry British "
                                       "butler who keeps it short”.")
        self.custom.setMaximumHeight(80)
        self.custom.textChanged.connect(self._custom_count)
        self.custom_count = QLabel()
        self.custom_count.setProperty("muted", True)
        personality_layout.addWidget(self.personality)
        personality_layout.addWidget(self.custom)
        personality_layout.addWidget(self.custom_count, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(personality_box)

        look_box = QGroupBox("Appearance")
        look_form = QFormLayout(look_box)
        self.theme = QComboBox()
        for name in THEMES:
            self.theme.addItem({"system": "Match Windows"}.get(name, name.capitalize()), name)
        accents = QHBoxLayout()
        self.accent_group = QButtonGroup(self)
        self.accent_buttons: dict[str, QPushButton] = {}
        for name, color in ACCENTS.items():
            button = self._swatch(color, name)
            self.accent_group.addButton(button)
            self.accent_buttons[color] = button
            accents.addWidget(button)
        self.custom_accent = QPushButton("Custom…")
        self.custom_accent.clicked.connect(self._pick_accent)
        accents.addWidget(self.custom_accent)
        accents.addStretch(1)
        self.accent = ACCENTS["Violet"]
        look_form.addRow("Theme", self.theme)
        look_form.addRow("Accent colour", accents)
        layout.addWidget(look_box)

        skills_box = QGroupBox("Skills")
        grid = QGridLayout(skills_box)
        self.skills: dict[str, QCheckBox] = {}
        groups = registry.groups() if registry is not None else {}
        for index, group in enumerate(TOOL_GROUPS):
            box = QCheckBox(SKILLS.get(group, group))
            tools = groups.get(group)
            tip = f"Tools: {', '.join(tools)}" if tools else ""
            if group in NEEDS_SAFETY:
                tip = (tip + "\n" if tip else "") + ("Also needs the matching switch in "
                                                     "Settings → Safety (off by default).")
            box.setToolTip(tip)
            self.skills[group] = box
            grid.addWidget(box, index // 2, index % 2)
        layout.addWidget(skills_box)
        layout.addStretch(1)

    def _swatch(self, color: str, name: str) -> QPushButton:
        button = QPushButton()
        button.setCheckable(True)
        button.setFixedSize(28, 28)
        button.setToolTip(name)
        button.setAccessibleName(f"{name} accent")
        button.setStyleSheet(
            f"QPushButton {{ background: {color}; border-radius: 14px; border: 2px solid "
            f"transparent; }} QPushButton:checked {{ border: 2px solid palette(text); }}")
        button.clicked.connect(lambda _c=False, c=color: self._set_accent(c))
        return button

    def _set_accent(self, color: str) -> None:
        self.accent = QColor(color).name()
        known = self.accent_buttons.get(self.accent)
        self.accent_group.setExclusive(False)
        for button in self.accent_buttons.values():
            button.setChecked(button is known)
        self.accent_group.setExclusive(True)
        self.custom_accent.setText("Custom…" if known else f"Custom {self.accent}")

    def _pick_accent(self) -> None:
        color = QColorDialog.getColor(QColor(self.accent), self, "Accent colour")
        if color.isValid():
            self._set_accent(color.name())

    def _sync_custom(self) -> None:
        custom = self.personality.currentData() == "custom"
        self.custom.setVisible(custom)
        self.custom_count.setVisible(custom)

    def _custom_count(self) -> None:
        length = len(self.custom.toPlainText())
        self.custom_count.setText(f"{length}/{CUSTOM_PERSONALITY_MAX}")

    def load(self, settings: Settings) -> None:
        loadout = settings.loadout
        self.voice.setCurrentText(loadout.voice)
        self.personality.setCurrentIndex(max(0, self.personality.findData(loadout.personality)))
        self.custom.setPlainText(loadout.custom_personality)
        self.theme.setCurrentIndex(max(0, self.theme.findData(loadout.theme)))
        self._set_accent(loadout.accent)
        for group, box in self.skills.items():
            box.setChecked(group in loadout.skills)
        self._sync_custom()
        self._custom_count()

    def apply(self, settings: Settings) -> None:
        loadout = settings.loadout
        loadout.voice = self.voice.currentText()
        loadout.personality = self.personality.currentData()
        loadout.custom_personality = self.custom.toPlainText().strip()
        loadout.theme = self.theme.currentData()
        loadout.accent = self.accent
        loadout.skills = [g for g, box in self.skills.items() if box.isChecked()]
