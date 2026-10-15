"""Images for Screen Assist (D-052): fewer tokens, and telling whether the screen changed.

* ``trim``: drop near-uniform borders (empty margins around a document, a blank sidebar) so
  the model's pixels go to content. ``downscale``: at most ``max_edge`` pixels on the long side;
  Gemini tiles larger images into 768 px tiles of 258 tokens each, so a window at 1024 px costs
  a handful of tiles, not dozens.
* ``fingerprint`` / ``changed``: the image's average brightness on a 64×40 grid (each cell the
  mean of its pixels). ``distance`` is the share of cells whose brightness moved by more than
  CELL_DELTA levels. Unlike a window title it notices new content in the same window (an error
  dialog, a test run finishing, a paragraph rewritten); unlike a pixel diff it ignores a blinking
  caret (one cell), a ticking clock or compression noise. A gradient hash (dHash) was tried
  first and missed a large dialog on a flat background: neighbouring cells of a flat app are
  nearly equal, so their comparison bits are noise.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageChops

MAX_EDGE = 1024  # on demand
WATCH_MAX_EDGE = 768  # Watch mode: one tile's width, cheaper
JPEG_QUALITY = 72
GRID = (64, 40)
CELL_DELTA = 10  # brightness levels (0–255) a cell must move to count as changed
FOLLOW_UP_CHANGE = 0.02  # a follow-up re-captures when more than this share of cells changed
WATCH_CHANGE = 0.01  # Watch mode analyses only beyond this (about 25 cells)


def trim(image: Image.Image, tolerance: int = 12, keep: int = 8) -> Image.Image:
    """Crop away borders that are all (nearly) the colour of the top-left pixel."""
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    difference = ImageChops.difference(rgb, background).convert("L")
    box = difference.point(lambda value: 255 if value > tolerance else 0).getbbox()
    if box is None:
        return image
    left, top, right, bottom = box
    width, height = image.size
    box = (max(0, left - keep), max(0, top - keep), min(width, right + keep),
           min(height, bottom + keep))
    if (box[2] - box[0]) * (box[3] - box[1]) > 0.92 * width * height:
        return image  # nothing worth cropping
    return image.crop(box)


def downscale(image: Image.Image, max_edge: int = MAX_EDGE) -> Image.Image:
    copy = image.convert("RGB")
    copy.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return copy


def jpeg(image: Image.Image, quality: int = JPEG_QUALITY) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def fingerprint(image: Image.Image, grid: tuple[int, int] = GRID) -> bytes:
    """Average brightness per cell (BOX resampling averages each cell's pixels)."""
    return image.convert("L").resize(grid, Image.Resampling.BOX).tobytes()


def distance(a: bytes, b: bytes) -> float:
    """Share of cells whose brightness moved by more than CELL_DELTA (1.0 if not comparable)."""
    if len(a) != len(b) or not a:
        return 1.0
    before = np.frombuffer(a, dtype=np.uint8).astype(np.int16)
    after = np.frombuffer(b, dtype=np.uint8).astype(np.int16)
    return float(np.count_nonzero(np.abs(before - after) > CELL_DELTA)) / len(a)


def changed(before: bytes | None, after: bytes, threshold: float) -> bool:
    return before is None or distance(before, after) > threshold
