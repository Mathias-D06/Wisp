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
FONT_MONO = ["Cascadia Mono", "Consolas", "Courier New"]  # code in answers (D-052)
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


# ----- the island (D-045) ------------------------------------------------------------------------
@dataclass(frozen=True)
class SpringTokens:
    stiffness: float  # k, with unit mass: angular frequency ω = √k
    damping_ratio: float  # ζ: < 1 may overshoot, 1 = critically damped (never overshoots)


@dataclass(frozen=True)
class IslandTokens:
    """Every size, spring and timing of the island, in logical px and milliseconds."""

    top: int = 6  # gap between the screen's top edge and the pill
    idle: tuple[int, int] = (180, 32)
    activity_height: int = 36
    activity_widths: tuple[tuple[str, int], ...] = (
        ("listening", 300), ("thinking", 280), ("speaking", 380), ("dictation", 300),
        ("status", 320), ("music", 300), ("countdown", 280))
    split_diameter: int = 36  # the detached circle of the split state
    split_gap: int = 8
    banner: tuple[int, int] = (400, 76)
    expanded: tuple[int, int] = (720, 580)
    expanded_radius: int = 26  # compact shapes are capsules: radius = height / 2
    hover_scale: float = 1.04
    shadow_margin: int = 40  # canvas room around the largest shape for the soft shadow
    shadow_blur: int = 28
    shadow_alpha: int = 110
    highlight_alpha: int = 28  # the 1 px inner highlight on the black fill
    content_scale: float = 0.96  # outgoing content shrinks to this, incoming grows from it
    expand: SpringTokens = SpringTokens(450.0, 0.82)  # ~1 % overshoot, settles in ~0.45 s
    collapse: SpringTokens = SpringTokens(600.0, 1.0)  # critically damped, clamped
    small: SpringTokens = SpringTokens(700.0, 0.9)  # width/height changes under small_px
    small_px: int = 60
    content_out_ms: int = 120
    content_in_ms: int = 180
    content_delay_ms: int = 40  # incoming content starts slightly after the shape moves
    row_stagger_ms: int = 20  # expanded panel rows
    crossfade_ms: int = 100  # replaces springs when motion is off
    hover_hold_ms: int = 300  # hover this long (or click) to expand
    collapse_delay_ms: int = 500  # after the pointer leaves the expanded panel
    banner_hold_ms: int = 3000
    banner_hover_extra_ms: int = 1500  # banner stays this long after the pointer leaves it
    banner_max_age_ms: int = 30000  # a queued banner older than this is dropped
    banner_queue: int = 5
    autohide_ms: int = 6000  # idle this long → slides away (Settings: 3–15 s; D-049)
    away_lift: int = 10  # px above the screen edge the hidden shape rests at
    reveal_margin: int = 40  # the reveal hot zone: the idle pill's width plus this each side…
    reveal_height: int = 3  # …and this many px from the screen's top edge
    reveal_dwell_ms: int = 150  # the pointer must rest in the zone this long
    reveal_poll_ms: int = 33  # cursor polling while hidden (~30 Hz)
    countdown_window_s: int = 600  # show a countdown for reminders due within 10 minutes
    idle_frame_ms: int = 125  # the orb's slow glow (8 fps); everything else is 16 ms
    meter_frame_ms: int = 50  # music equaliser (20 fps)
    fullscreen_poll_ms: int = 1000

    def activity_width(self, kind: str) -> int:
        return dict(self.activity_widths).get(kind, 300)


ISLAND = IslandTokens()


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
    """A pixel-sized font for widgets and painters that set their own font."""
    font = QFont()
    font.setFamilies(families(size))
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    return font


def app_font(size: int = BODY) -> QFont:
    """The application's default font, sized in points. A pixel-sized font reports a point size
    of -1, and Qt widgets that copy the default font's point size (QCalendarWidget, behind
    QDateTimeEdit's calendar popup) would pass that on: "QFont::setPointSize: Point size <= 0".
    The point size comes from the screen's logical DPI (QScreen: "used to convert font point
    sizes to pixel sizes"), so the text is exactly ``size`` px, as with ui_font."""
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.primaryScreen() if QGuiApplication.instance() else None
    dpi = screen.logicalDotsPerInchY() if screen is not None else 96.0
    font = QFont()
    font.setFamilies(families(size))
    font.setPointSizeF(size * 72.0 / (dpi or 96.0))
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
    QScrollArea > QWidget > QWidget#ScrollList {{ background: transparent; }}
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


DARK_SURFACE_PROPERTY = "darkSurface"  # set on the island: it is black in either theme (D-045)


def palette_for(widget: QWidget | None) -> Palette:
    """The palette a widget is drawn with: the app's, or the dark one inside a widget marked
    with DARK_SURFACE_PROPERTY (the island)."""
    while widget is not None:
        if widget.property(DARK_SURFACE_PROPERTY):
            app = current()
            return app if app.dark else palette("dark", app.accent)
        widget = widget.parentWidget()
    return current()
