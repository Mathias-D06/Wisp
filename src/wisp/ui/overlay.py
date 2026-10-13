"""Circle to Ask overlay: one frameless window per screen showing a frozen screenshot.

Multi-monitor and DPI handling (doc.qt.io/qt-6/highdpi.html, /qscreen.html): every QScreen gets
its own overlay sized to ``screen.geometry()`` (device-independent pixels; Windows screens can form
"islands", so no single window spans monitors). The screenshot comes from
``screen.grabWindow(0)`` *before* the overlay appears and is in physical pixels, so a loop drawn in
overlay coordinates maps to the image by the ratio pixmap size / geometry size on that screen.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QScreen
from PySide6.QtWidgets import QWidget

from wisp.ui import theme

PADDING = 12  # logical pixels added around the loop
MIN_SIZE = 24
MAX_EDGE = 1280
JPEG_QUALITY = 80


def map_to_pixmap(bbox: QRectF, geometry: QRect, pixmap_width: int,
                  pixmap_height: int) -> QRect:
    """Logical bbox (global coords) → pixel rect inside the screen's screenshot."""
    sx = pixmap_width / max(1, geometry.width())
    sy = pixmap_height / max(1, geometry.height())
    left = (bbox.left() - geometry.x()) * sx
    top = (bbox.top() - geometry.y()) * sy
    rect = QRect(int(left), int(top), round(bbox.width() * sx),
                 round(bbox.height() * sy))
    return rect.intersected(QRect(0, 0, pixmap_width, pixmap_height))


def encode_jpeg(pixmap: QPixmap, max_edge: int = MAX_EDGE) -> bytes:
    if max(pixmap.width(), pixmap.height()) > max_edge:
        pixmap = pixmap.scaled(max_edge, max_edge, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "JPG", JPEG_QUALITY)
    buffer.close()
    return bytes(data.data())


class CircleOverlay(QWidget):
    stroked = Signal()

    def __init__(self, screen: QScreen, shot: QPixmap, accent: str):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        if shot.isNull():
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.screen_ref = screen
        self.shot = shot
        self.accent = QColor(accent)
        self.strokes: list[list[QPointF]] = []
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())

    # ----- drawing -----------------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.strokes.append([event.position()])
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.strokes and event.buttons() & Qt.MouseButton.LeftButton:
            self.strokes[-1].append(event.position())
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.strokes:
            self.stroked.emit()

    def has_stroke(self) -> bool:
        return any(len(stroke) >= 2 for stroke in self.strokes)

    def local_bbox(self) -> QRectF | None:
        points = [p for stroke in self.strokes for p in stroke]
        if len(points) < 2:
            return None
        xs = [p.x() for p in points]
        ys = [p.y() for p in points]
        box = QRectF(min(xs) - PADDING, min(ys) - PADDING,
                     max(xs) - min(xs) + 2 * PADDING, max(ys) - min(ys) + 2 * PADDING)
        if box.width() < MIN_SIZE:
            box.adjust(-(MIN_SIZE - box.width()) / 2, 0, (MIN_SIZE - box.width()) / 2, 0)
        if box.height() < MIN_SIZE:
            box.adjust(0, -(MIN_SIZE - box.height()) / 2, 0, (MIN_SIZE - box.height()) / 2)
        return box.intersected(QRectF(self.rect()))

    def global_bbox(self) -> QRectF | None:
        box = self.local_bbox()
        if box is None:
            return None
        origin = self.screen_ref.geometry().topLeft()
        return box.translated(origin.x(), origin.y())

    def crop(self, shot: QPixmap | None = None) -> tuple[bytes, QRect] | None:
        """JPEG of the circled area and its global logical rectangle."""
        box = self.global_bbox()
        source = shot if shot is not None else self.shot
        if box is None or source.isNull():
            return None
        rect = map_to_pixmap(box, self.screen_ref.geometry(), source.width(), source.height())
        if rect.isEmpty():
            return None
        return encode_jpeg(source.copy(rect)), box.toAlignedRect()

    def _paint_hint(self, painter: QPainter) -> None:
        """A small token-styled pill at the top: what to do."""
        p = theme.current()
        painter.save()  # the pill's brush must not fill the user's loop afterwards
        text = "Circle what you want to ask about, and say your question"
        painter.setFont(theme.ui_font(theme.BODY))
        width = painter.fontMetrics().horizontalAdvance(text) + 2 * theme.SPACE["l"]
        pill = QRectF((self.width() - width) / 2, 20, width, 34)
        background = QColor(p.surface2)
        background.setAlphaF(0.94)
        painter.setPen(QColor(p.border))
        painter.setBrush(background)
        painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        painter.setPen(QColor(p.text))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.shot.isNull():
            painter.drawPixmap(self.rect(), self.shot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 70))
        self._paint_hint(painter)
        glow = QColor(self.accent)
        glow.setAlpha(90)
        for color, width in ((glow, 12), (self.accent, 4)):
            pen = QPen(color, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            for stroke in self.strokes:
                if len(stroke) < 2:
                    continue
                path = QPainterPath(stroke[0])
                for point in stroke[1:]:
                    path.lineTo(point)
                painter.drawPath(path)
        painter.end()
