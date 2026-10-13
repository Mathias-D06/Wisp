"""Island geometry (D-045): target sizes per presentation, the shape's rectangles inside the
fixed canvas, its corner radius, and the input region that lets clicks beside it through.

All values are logical (device-independent) pixels; Qt maps them to device pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QRegion

from wisp.ui.island.machine import Presentation
from wisp.ui.theme import ISLAND, IslandTokens

AA_MARGIN = 1  # px of the input region beyond the shape, so antialiased edge pixels count


@dataclass(frozen=True)
class ShapeTarget:
    width: float
    height: float
    split: float = 0.0  # diameter of the detached circle (0 = no split)
    gap: float = 0.0  # space between the pill and the circle


def target_for(p: Presentation, hover: bool = False, tokens: IslandTokens = ISLAND) -> ShapeTarget:
    grow = tokens.hover_scale if hover else 1.0
    if p.mode == "sliver":
        return ShapeTarget(*tokens.sliver)
    if p.mode == "banner":
        return ShapeTarget(*tokens.banner)
    if p.mode == "expanded":
        return ShapeTarget(*tokens.expanded)
    if p.mode == "activity" and p.main is not None:
        width = tokens.activity_width(p.main.kind) * grow
        height = tokens.activity_height * grow
        if p.secondary is not None:
            return ShapeTarget(width, height, tokens.split_diameter * grow, tokens.split_gap)
        return ShapeTarget(width, height)
    width, height = tokens.idle  # idle and hidden (the island reappears from idle)
    return ShapeTarget(width * grow, height * grow)


def corner_radius(height: float, tokens: IslandTokens = ISLAND) -> float:
    """A capsule while compact (half the height); expanded shapes settle at expanded_radius."""
    return max(0.0, min(height / 2, tokens.expanded_radius))


def canvas_size(tokens: IslandTokens = ISLAND) -> tuple[int, int]:
    """One fixed transparent canvas big enough for every state plus its shadow (the native
    window is never resized while the shape morphs)."""
    widest_activity = max(width for _kind, width in tokens.activity_widths)
    split = widest_activity * tokens.hover_scale + tokens.split_gap \
        + tokens.split_diameter * tokens.hover_scale
    width = max(tokens.expanded[0], tokens.banner[0], split) * 1.04  # spring overshoot room
    height = tokens.top + tokens.expanded[1] * 1.04
    margin = tokens.shadow_margin
    return int(width + 2 * margin + 0.5), int(height + margin + 0.5)


def shape_rects(canvas_width: float, top: float, width: float, height: float,
                split: float = 0.0, gap: float = 0.0) -> tuple[QRectF, QRectF | None]:
    """The pill and the split circle, centred as a group at the top of the canvas."""
    has_circle = split >= 1.0
    total = width + (gap + split if has_circle else 0.0)
    left = (canvas_width - total) / 2
    main = QRectF(left, top, width, height)
    if not has_circle:
        return main, None
    circle = QRectF(main.right() + gap, main.center().y() - split / 2, split, split)
    return main, circle


def rounded_region(rect: QRectF, radius: float, grow: float = AA_MARGIN) -> QRegion:
    """A rounded rectangle as a QRegion (two rectangles plus four corner discs), grown by
    ``grow`` px so the antialiased edge stays inside."""
    r = rect.adjusted(-grow, -grow, grow, grow).toAlignedRect()
    radius = min(radius + grow, r.width() / 2, r.height() / 2)
    d = round(2 * radius)
    if d < 2:
        return QRegion(r)
    region = QRegion(r.adjusted(d // 2, 0, -(d // 2), 0)).united(
        QRegion(r.adjusted(0, d // 2, 0, -(d // 2))))
    for x, y in ((r.left(), r.top()), (r.right() - d + 1, r.top()),
                 (r.left(), r.bottom() - d + 1), (r.right() - d + 1, r.bottom() - d + 1)):
        region = region.united(QRegion(QRect(x, y, d, d), QRegion.RegionType.Ellipse))
    return region


def input_region(main: QRectF, circle: QRectF | None = None,
                 tokens: IslandTokens = ISLAND) -> QRegion:
    """Where the island takes mouse input: exactly its visible shape (QWindow.setMask). Clicks
    anywhere else on the canvas, including just beside the pill, reach the app underneath."""
    region = rounded_region(main, corner_radius(main.height(), tokens))
    if circle is not None and circle.width() >= 1.0:
        region = region.united(rounded_region(circle, circle.width() / 2))
    return region
