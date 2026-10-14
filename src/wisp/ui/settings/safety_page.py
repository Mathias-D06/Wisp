"""Settings → Safety: risky skills (terminal, raw input), which confirmations may be skipped, and
the untrusted-content window (F12.3, F12.4; DECISIONS.md D-012, D-034)."""

from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from wisp.settings import NEVER_AUTO_APPROVE, Settings
from wisp.tools.base import Risk
from wisp.ui.settings.base import SettingsPage, hint

RISKY_SKILLS = [
    ("allow_terminal", "terminal", "Allow terminal commands",
     "Wisp may run PowerShell commands as you. Every command is shown and needs your yes."),
    ("allow_raw_input", "input", "Allow raw mouse and keyboard control",
     "Wisp may click at screen positions and press keys. Clicks and risky keys (Enter, Delete, "
     "Alt+F4…) need your yes."),
]
LIMITS = ("Wisp never tries to get past UAC prompts, the lock screen or the Ctrl+Alt+Del "
          "screen, never controls apps running as administrator (unless Wisp itself does), and "
          "won't send keys or clicks to a full-screen game while anti-cheat software is "
          "running. It tells you instead.")


def auto_approvable(registry) -> list:
    """Tools that can ever be confirm-tier and are allowed to skip confirmation."""
    result = []
    for tool in registry.all() if registry is not None else []:
        if tool.name in NEVER_AUTO_APPROVE or tool.risk == Risk.DISABLED:
            continue
        if tool.risk == Risk.CONFIRM or tool.risk_fn is not None:
            result.append(tool)
    return result


def short(description: str) -> str:
    first = re.split(r"\. |, e\.g\.| \(", description)[0].rstrip(".")
    return first[:1].lower() + first[1:]


def never_labels(registry) -> list[str]:
    tools = {t.name: t for t in registry.all()} if registry is not None else {}
    return sorted(short(tools[n].description) if n in tools else n for n in NEVER_AUTO_APPROVE)


class SafetyPage(SettingsPage):
    title = "Safety"

    def __init__(self, registry=None):
        super().__init__()
        self.registry = registry
        self._loaded: dict[str, bool] = {}
        layout = QVBoxLayout(self)
        layout.addWidget(hint(LIMITS))

        risky = QGroupBox("Risky skills (off by default)")
        risky_layout = QVBoxLayout(risky)
        self.toggles: dict[str, QCheckBox] = {}
        for flag, _skill, label, explanation in RISKY_SKILLS:
            box = QCheckBox(label)
            self.toggles[flag] = box
            risky_layout.addWidget(box)
            risky_layout.addWidget(hint(explanation))
        layout.addWidget(risky)

        approve = QGroupBox("Skip confirmation for")
        approve_layout = QVBoxLayout(approve)
        approve_layout.addWidget(hint(
            "Only for requests you make by voice or in the console, and never within the "
            "untrusted-content window below. Routines always ask with a card."))
        self.auto: dict[str, QCheckBox] = {}
        for tool in auto_approvable(registry):
            box = QCheckBox(tool.description.split(".")[0])
            box.setToolTip(tool.name)
            self.auto[tool.name] = box
            approve_layout.addWidget(box)
        if not self.auto:
            approve_layout.addWidget(QLabel("No actions can skip confirmation."))
        approve_layout.addWidget(hint("Always ask, whatever you choose: "
                                      + "; ".join(never_labels(registry)) + "."))
        layout.addWidget(approve)

        taint = QGroupBox("Untrusted content")
        form = QFormLayout(taint)
        self.taint_minutes = QSpinBox()
        self.taint_minutes.setRange(1, 120)
        self.taint_minutes.setSuffix(" min")
        form.addRow("After Wisp reads the screen, a file or a web page, ask before every "
                    "risky action for", self.taint_minutes)
        layout.addWidget(taint)

        phone = QGroupBox("Phone link")
        phone_form = QFormLayout(phone)
        self.phone_max_mb = QSpinBox()
        self.phone_max_mb.setRange(1, 20480)
        self.phone_max_mb.setSingleStep(100)
        self.phone_max_mb.setSuffix(" MB")
        phone_form.addRow("Largest file a phone may send", self.phone_max_mb)
        phone_form.addRow(hint("The phone link only opens on a Private network, stops after 10 "
                               "minutes, and every file from the phone needs your OK. Files "
                               "arrive in Downloads\\Wisp."))
        layout.addWidget(phone)
        layout.addStretch(1)

    def load(self, settings: Settings) -> None:
        safety = settings.safety
        for flag, box in self.toggles.items():
            self._loaded[flag] = getattr(safety, flag)
            box.setChecked(getattr(safety, flag))
        for name, box in self.auto.items():
            box.setChecked(name in safety.auto_approve)
        self.taint_minutes.setValue(safety.taint_minutes)
        self.phone_max_mb.setValue(settings.share.phone_max_upload_mb)

    def apply(self, settings: Settings) -> None:
        safety = settings.safety
        for flag, skill, _label, _explanation in RISKY_SKILLS:
            enabled = self.toggles[flag].isChecked()
            setattr(safety, flag, enabled)
            # Switching a risky skill on here also ticks its Loadout skill (it needs both).
            if enabled and not self._loaded.get(flag) and skill not in settings.loadout.skills:
                settings.loadout.skills.append(skill)
            self._loaded[flag] = enabled
        # Names this page doesn't show are kept, except ones that may never skip confirmation.
        kept = [n for n in safety.auto_approve
                if n not in self.auto and n not in NEVER_AUTO_APPROVE]
        safety.auto_approve = kept + [n for n, box in self.auto.items() if box.isChecked()]
        safety.taint_minutes = self.taint_minutes.value()
        settings.share.phone_max_upload_mb = self.phone_max_mb.value()
