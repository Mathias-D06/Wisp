"""Design tokens and the one stylesheet every Wisp window uses (Appearance slot; D-043).

Tokens: colours (a near-black, slightly cool base; two elevated surfaces; three text levels;
one accent used sparingly), type (Segoe UI Variable → Segoe UI, scale 12/13/15/20 px, weights
400/600), spacing (4/8 px grid), radii (8 px controls, 12 px panels), shadows and motion
(``motion.py``). Text colours meet WCAG AA (4.5:1) on every surface, which a test checks.
"""

from __future__ import annotations

import winreg
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractScrollArea, QWidget

THEMES = ["dark", "light", "system"]
ACCENTS = {
    "Violet": "#7c5cff",
    "Teal": "#14b8a6",
    "Amber": "#f59e0b",
    "Rose": "#f43f5e",
    "Sky": "#38bdf8",
    "Lime": "#84cc16",
}

# ----- type ---------------------------------------------------------------------------------------
FONT_SMALL = ["Segoe UI Variable Small", "Segoe UI"]
FONT_TEXT = ["Segoe UI Variable Text", "Segoe UI"]
FONT_DISPLAY = ["Segoe UI Variable Display", "Segoe UI"]
CAPTION, BODY, TITLE, DISPLAY = 12, 13, 15, 20  # px
REGULAR, SEMIBOLD = 400, 600  # Semibold only for titles (TITLE and up)
LINE_HEIGHT = 1.45  # transcript and long text


def families(size: int) -> list[str]:
    """The Segoe UI Variable optical cut Windows' type ramp uses at this size: Small for captions,
    Text for body, Display from 20 px. Segoe UI where Segoe UI Variable is missing (Windows 10)."""
    if size <= CAPTION:
        return FONT_SMALL
    return FONT_DISPLAY if size >= DISPLAY else FONT_TEXT


def font_css(size: int) -> str:
    family = ", ".join(f"'{f}'" for f in families(size))
    return f"font-family: {family}; font-size: {size}px;"

# ----- spacing and shape ------------------------------------------------------------------------
SPACE = {"xs": 4, "s": 8, "m": 12, "l": 16, "xl": 24}
RADIUS_CONTROL = 8
RADIUS_PANEL = 12
ICON_SM, ICON_MD = 16, 20

# ----- elevation ---------------------------------------------------------------------------------
SHADOW_BLUR, SHADOW_Y = 24, 4  # fits the 10 px margin around frameless popups


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str  # window base
    surface: str  # panels, cards
    surface2: str  # controls, raised
    hover: str
    pressed: str
    text: str  # primary
    secondary: str
    muted: str
    border: str  # solid hairline (painted)
    hairline: str  # low-opacity hairline (stylesheets)
    accent: str
    accent_fill: str  # accent shade that carries text at AA contrast
    accent_text: str
    accent_soft: str  # selection / active backgrounds
    danger: str
    success: str
    warning: str
    scrim: str
    shadow_alpha: int


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


# ----- contrast (WCAG 2.x relative luminance) ---------------------------------------------------
def luminance(color: str) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    c = QColor(color)
    return 0.2126 * channel(c.redF()) + 0.7152 * channel(c.greenF()) + 0.0722 * channel(c.blueF())


def contrast(foreground: str, background: str) -> float:
    a, b = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def rgba(color: str, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.2f})"


def accent_pair(accent: str) -> tuple[str, str]:
    """(fill, text) for filled accent buttons at ≥ 4.5:1: light accents get dark text, others
    get white text on a fill darkened just enough."""
    dark_text, white = "#101216", "#ffffff"
    if luminance(accent) > 0.3:
        return accent, dark_text
    fill = QColor(accent)
    while contrast(white, fill.name()) < 4.5 and fill.lightness() > 20:
        fill = fill.darker(106)
    return fill.name(), white


def palette(theme: str, accent: str) -> Palette:
    dark = system_prefers_dark() if theme == "system" else theme != "light"
    if not QColor(accent).isValid():
        accent = ACCENTS["Violet"]
    fill, fill_text = accent_pair(accent)
    if dark:
        return Palette(
            dark=True, bg="#0e0f13", surface="#16181d", surface2="#1f2128", hover="#262932",
            pressed="#2c303a", text="#eceef2", secondary="#b6bac4", muted="#9196a3",
            border="#2a2d36", hairline=rgba("#ffffff", 0.08), accent=accent, accent_fill=fill,
            accent_text=fill_text, accent_soft=rgba(accent, 0.18), danger="#f87171",
            success="#4ade80", warning="#fbbf24", scrim=rgba("#000000", 0.45), shadow_alpha=110,
        )
    return Palette(
        dark=False, bg="#f4f5f8", surface="#ffffff", surface2="#eef0f4", hover="#e6e9ef",
        pressed="#dde1e8", text="#14161b", secondary="#3d424d", muted="#596070",
        border="#d9dce3", hairline=rgba("#000000", 0.09), accent=accent, accent_fill=fill,
        accent_text=fill_text, accent_soft=rgba(accent, 0.14), danger="#c42121",
        success="#136c33", warning="#8f4f05", scrim=rgba("#000000", 0.30), shadow_alpha=45,
    )


def ui_font(size: int = BODY, weight: int = REGULAR) -> QFont:
    font = QFont()
    font.setFamilies(families(size))
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    return font


# ----- stylesheet ---------------------------------------------------------------------------------
def _icon_url(name: str, color: str, folder: Path) -> str:
    from wisp.ui.iconset import write_tinted

    return write_tinted(name, color, folder).as_posix()


def icon_cache_dir() -> Path:
    from wisp import paths

    return paths.data_dir() / "cache" / "icons"


def stylesheet(p: Palette) -> str:
    cache = icon_cache_dir()
    check = _icon_url("check", p.accent_text, cache)
    down = _icon_url("chevron-down", p.secondary, cache)
    up = _icon_url("chevron-up", p.secondary, cache)
    rc, rp = RADIUS_CONTROL, RADIUS_PANEL
    return f"""
    QWidget {{ color: {p.text}; {font_css(BODY)} }}
    QDialog, QMainWindow, QWidget#Window {{ background: {p.bg}; }}
    QDialog[mica="true"], QWidget#Window[mica="true"] {{ background: transparent; }}
    QToolTip {{ background: {p.surface2}; color: {p.text}; border: 1px solid {p.hairline};
        border-radius: 6px; padding: 4px 8px; }}

    QTabWidget::pane {{ border: 1px solid {p.hairline}; border-radius: {rp}px;
        background: {p.surface}; top: -1px; }}
    QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget#SettingsPage {{ background: transparent; }}
    QTabBar::tab {{ background: transparent; color: {p.secondary}; padding: 6px 12px;
        margin: 0 2px 6px 0; border: none; border-radius: {rc}px; }}
    QTabBar::tab:hover {{ color: {p.text}; background: {p.hover}; }}
    QTabBar::tab:selected {{ color: {p.text}; background: {p.surface2}; }}

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QTimeEdit, QDateTimeEdit {{
        background: {p.surface2}; border: 1px solid {p.hairline}; border-radius: {rc}px;
        padding: 6px 10px; selection-background-color: {p.accent_fill};
        selection-color: {p.accent_text};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus,
    QTimeEdit:focus, QDateTimeEdit:focus {{ border: 1px solid {p.accent}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {p.muted}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: url({down}); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{ background: {p.surface2}; border: 1px solid {p.hairline};
        border-radius: {rc}px; padding: 4px; outline: none;
        selection-background-color: {p.accent_soft}; selection-color: {p.text}; }}
    QSpinBox::up-button, QSpinBox::down-button, QTimeEdit::up-button, QTimeEdit::down-button,
    QDateTimeEdit::up-button, QDateTimeEdit::down-button {{ border: none; width: 20px; }}
    QSpinBox::up-arrow, QTimeEdit::up-arrow, QDateTimeEdit::up-arrow {{ image: url({up});
        width: 12px; height: 12px; }}
    QSpinBox::down-arrow, QTimeEdit::down-arrow, QDateTimeEdit::down-arrow {{
        image: url({down}); width: 12px; height: 12px; }}

    QListWidget, QTableWidget, QTreeView, QListView {{ background: {p.surface};
        border: 1px solid {p.hairline}; border-radius: {rc}px; outline: none;
        selection-background-color: {p.accent_soft}; selection-color: {p.text}; }}
    QListWidget::item, QTableWidget::item {{ padding: 4px; }}
    QHeaderView::section {{ background: {p.surface}; color: {p.secondary}; border: none;
        border-bottom: 1px solid {p.hairline}; padding: 6px; {font_css(CAPTION)} }}
    QTableCornerButton::section {{ background: {p.surface}; border: none; }}

    QPushButton {{ background: {p.surface2}; border: 1px solid {p.hairline};
        border-radius: {rc}px; padding: 6px 14px; }}
    QPushButton:hover {{ background: {p.hover}; }}
    QPushButton:pressed {{ background: {p.pressed}; }}
    QPushButton:focus {{ border: 1px solid {p.accent}; }}
    QPushButton:disabled {{ color: {p.muted}; }}
    QPushButton[primary="true"] {{ background: {p.accent_fill}; color: {p.accent_text};
        border: none; }}
    QPushButton[primary="true"]:hover {{ background: {QColor(p.accent_fill).lighter(110).name()}; }}
    QPushButton[primary="true"]:pressed {{ background: {QColor(p.accent_fill).darker(110).name()}; }}
    QPushButton[danger="true"] {{ color: {p.danger}; }}
    QToolButton#IconButton {{ background: transparent; border: none; border-radius: {rc}px;
        padding: 6px; }}
    QToolButton#IconButton:hover {{ background: {p.hover}; }}
    QToolButton#IconButton:pressed {{ background: {p.pressed}; }}
    QToolButton#IconButton:checked {{ background: {p.accent_soft}; }}

    QLabel[muted="true"] {{ color: {p.muted}; }}
    QLabel[secondary="true"] {{ color: {p.secondary}; }}
    QLabel[error="true"] {{ color: {p.danger}; }}
    QLabel[ok="true"] {{ color: {p.success}; }}
    QLabel[caption="true"] {{ {font_css(CAPTION)} }}
    QLabel[heading="true"] {{ {font_css(TITLE)} font-weight: {SEMIBOLD}; }}

    QGroupBox {{ background: {p.surface}; border: 1px solid {p.hairline}; border-radius: {rp}px;
        margin-top: 22px; padding: 12px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 2px; top: 0; color: {p.secondary};
        {font_css(CAPTION)} }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator, QAbstractItemView::indicator {{ width: 16px; height: 16px;
        border: 1px solid {p.muted}; border-radius: 4px; background: transparent; }}
    QCheckBox::indicator:hover {{ border-color: {p.secondary}; }}
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{
        background: {p.accent_fill}; border: 1px solid {p.accent_fill}; image: url({check}); }}

    QSlider::groove:horizontal {{ height: 4px; background: {p.border}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {p.text}; width: 14px; height: 14px;
        margin: -5px 0; border-radius: 7px; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: transparent; border-radius: 3px; min-height: 28px;
        min-width: 28px; }}
    QScrollBar[hovered="true"]::handle {{ background: {rgba(p.text, 0.22)}; }}
    QScrollBar[hovered="true"]::handle:hover {{ background: {rgba(p.text, 0.35)}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page,
    QScrollBar::sub-page {{ background: none; height: 0; width: 0; }}

    QMenu {{ background: {p.surface2}; border: 1px solid {p.hairline}; border-radius: {rc}px;
        padding: 4px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
    QMenu::separator {{ height: 1px; background: {p.hairline}; margin: 4px 8px; }}
    """


class ScrollbarReveal(QObject):
    """Thin scrollbars that only appear while the pointer is over their scroll area."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind in (QEvent.Type.Enter, QEvent.Type.Leave) and isinstance(watched,
                                                                          QAbstractScrollArea):
            shown = kind == QEvent.Type.Enter
            for bar in (watched.verticalScrollBar(), watched.horizontalScrollBar()):
                if bar.property("hovered") != shown:
                    bar.setProperty("hovered", shown)
                    bar.style().unpolish(bar)
                    bar.style().polish(bar)
        return False


_reveal = ScrollbarReveal()


def reveal_scrollbars(root: QWidget) -> None:
    """Install the hover reveal on every scroll area in ``root`` (call after building it)."""
    areas = root.findChildren(QAbstractScrollArea)
    if isinstance(root, QAbstractScrollArea):
        areas.append(root)
    for area in areas:
        if not area.property("_reveal"):
            area.setProperty("_reveal", True)
            area.installEventFilter(_reveal)


# ----- current palette (widgets re-tint their icons when it changes) ----------------------------
class _ThemeSignals(QObject):
    changed = Signal(object)  # Palette


signals = _ThemeSignals()
_current: Palette | None = None


def current() -> Palette:
    global _current
    if _current is None:
        _current = palette("dark", ACCENTS["Violet"])
    return _current


def set_current(p: Palette) -> None:
    global _current
    _current = p
    signals.changed.emit(p)
