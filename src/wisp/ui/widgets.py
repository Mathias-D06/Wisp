"""Small shared widgets built on the theme tokens: icon buttons and toggle switches."""

from __future__ import annotations

from PySide6.QtCore import Property, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCheckBox, QToolButton

from wisp.ui import iconset, motion, theme


class IconButton(QToolButton):
    """A borderless icon button (optionally checkable, with a second icon when checked)."""

    def __init__(self, icon: str, tooltip: str, size: int = theme.ICON_SM, *,
                 checked_icon: str | None = None, checkable: bool = False, text: str = "",
                 parent=None):
        super().__init__(parent)
        self.setObjectName("IconButton")
        self._icon, self._checked_icon = icon, checked_icon
        self.setIconSize(QSize(size, size))
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if text:
            self.setText(text)
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggled.connect(self.refresh)
        theme.signals.changed.connect(self.refresh)  # bound: dropped when the button is deleted
        self.refresh()

    def set_icon_name(self, name: str) -> None:
        self._icon = name
        self.refresh()

    def refresh(self, *_args) -> None:
        p = theme.palette_for(self)
        name = self._checked_icon if self.isChecked() and self._checked_icon else self._icon
        color = p.accent if self.isChecked() else p.secondary
        self.setIcon(iconset.icon(name, color, disabled=p.muted))


class ToggleSwitch(QCheckBox):
    """A switch with the QCheckBox API (checked/toggled); the knob slides when motion is on."""

    WIDTH, HEIGHT = 36, 20

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._offset = 0.0
        self.toggled.connect(self._slide)
        theme.signals.changed.connect(self._restyle)

    def _restyle(self, _palette) -> None:
        self.update()

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        self.update()

    def _slide(self, checked: bool) -> None:
        motion.animate(self, b"offset", self._offset, 1.0 if checked else 0.0, motion.FAST_MS)

    def sizeHint(self) -> QSize:
        text_width = self.fontMetrics().horizontalAdvance(self.text()) + 10 if self.text() else 0
        return QSize(self.WIDTH + text_width, max(self.HEIGHT, self.fontMetrics().height()) + 4)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:
        p = theme.palette_for(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        top = (self.height() - self.HEIGHT) / 2
        track = QRectF(0.5, top + 0.5, self.WIDTH - 1, self.HEIGHT - 1)
        off, on = QColor(p.surface2), QColor(p.accent_fill)
        mix = self._offset
        fill = QColor.fromRgbF(off.redF() + (on.redF() - off.redF()) * mix,
                               off.greenF() + (on.greenF() - off.greenF()) * mix,
                               off.blueF() + (on.blueF() - off.blueF()) * mix)
        painter.setBrush(fill)
        painter.setPen(QColor(p.muted) if mix < 0.5 else fill)
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        knob = self.HEIGHT - 8
        x = 4 + (self.WIDTH - 8 - knob) * mix
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.accent_text) if mix >= 0.5 else QColor(p.secondary))
        painter.drawEllipse(QRectF(x, top + 4, knob, knob))
        if self.text():
            painter.setPen(QColor(p.text) if self.isEnabled() else QColor(p.muted))
            painter.drawText(QRectF(self.WIDTH + 10, 0, self.width() - self.WIDTH - 10,
                                    self.height()),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             self.text())
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(p.accent))
            painter.drawRoundedRect(track.adjusted(-2, -2, 2, 2), track.height() / 2 + 2,
                                    track.height() / 2 + 2)
        painter.end()
