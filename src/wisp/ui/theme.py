"""Colour tokens and the shared Qt stylesheet (Appearance slot of the Loadout)."""

from __future__ import annotations

import winreg
from dataclasses import dataclass

from PySide6.QtGui import QColor

THEMES = ["dark", "light", "system"]
ACCENTS = {
    "Violet": "#7c5cff",
    "Teal": "#14b8a6",
    "Amber": "#f59e0b",
    "Rose": "#f43f5e",
    "Sky": "#38bdf8",
    "Lime": "#84cc16",
}


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    surface: str
    surface2: str
    text: str
    muted: str
    border: str
    accent: str
    accent_text: str
    danger: str
    success: str


def system_prefers_dark() -> bool:
    """Read the per-user app theme. A missing value means light (Windows default)."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
    except OSError:
        return False


def _readable_on(color: str) -> str:
    c = QColor(color)
    luminance = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
    return "#111111" if luminance > 0.6 else "#ffffff"


def palette(theme: str, accent: str) -> Palette:
    dark = system_prefers_dark() if theme == "system" else theme != "light"
    if not QColor(accent).isValid():
        accent = ACCENTS["Violet"]
    if dark:
        return Palette(
            dark=True, bg="#14141a", surface="#1d1d26", surface2="#272733", text="#f2f2f7",
            muted="#9a9aae", border="#33333f", accent=accent, accent_text=_readable_on(accent),
            danger="#f87171", success="#4ade80",
        )
    return Palette(
        dark=False, bg="#f6f6f9", surface="#ffffff", surface2="#ececf2", text="#16161d",
        muted="#5f5f70", border="#d8d8e2", accent=accent, accent_text=_readable_on(accent),
        danger="#dc2626", success="#16a34a",
    )


def stylesheet(p: Palette) -> str:
    return f"""
    QWidget {{ color: {p.text}; font-family: 'Segoe UI Variable Text', 'Segoe UI'; font-size: 10pt; }}
    QDialog, QMainWindow, QWidget#Window {{ background: {p.bg}; }}
    QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 8px; background: {p.surface}; }}
    QTabBar::tab {{ background: transparent; color: {p.muted}; padding: 6px 12px; border: none; }}
    QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.accent}; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QListWidget, QTableWidget,
    QTimeEdit, QDateTimeEdit {{
        background: {p.surface2}; border: 1px solid {p.border}; border-radius: 6px; padding: 4px 6px;
        selection-background-color: {p.accent}; selection-color: {p.accent_text};
    }}
    QHeaderView::section {{ background: {p.surface}; color: {p.muted}; border: none; padding: 4px; }}
    QPushButton {{
        background: {p.surface2}; border: 1px solid {p.border}; border-radius: 6px; padding: 5px 12px;
    }}
    QPushButton:hover {{ border-color: {p.accent}; }}
    QPushButton:disabled {{ color: {p.muted}; }}
    QPushButton[primary="true"] {{ background: {p.accent}; color: {p.accent_text}; border: none; }}
    QPushButton[danger="true"] {{ color: {p.danger}; }}
    QLabel[muted="true"] {{ color: {p.muted}; }}
    QLabel[error="true"] {{ color: {p.danger}; }}
    QLabel[ok="true"] {{ color: {p.success}; }}
    QGroupBox {{ border: 1px solid {p.border}; border-radius: 8px; margin-top: 14px; padding: 8px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {p.muted}; }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border: 1px solid {p.accent}; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {p.border}; border-radius: 3px; }}
    QSlider::groove:horizontal {{ height: 4px; background: {p.border}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {p.text}; width: 12px; margin: -5px 0; border-radius: 6px; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 24px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QMenu {{ background: {p.surface}; border: 1px solid {p.border}; }}
    QMenu::item:selected {{ background: {p.accent}; color: {p.accent_text}; }}
    """
