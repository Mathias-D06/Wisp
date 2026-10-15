"""Dev helper: a made-up Screen Assist exchange for screenshots and recordings (D-052).

The "screenshot" is drawn here (a small code editor with an error), and the answers are
written out below: nothing from this PC's screen is captured and nothing is sent to Gemini.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from wisp.assist import imaging
from wisp.assist.engine import Exchange, Shot

CODE = [
    "def total(prices, quantities):",
    "    total = 0",
    "    for i in range(len(prices)):",
    "        total += prices[i] * quantity[i]",
    "    return total",
    "",
    "print(total([2.5, 4.0], [3, 1]))",
]
ERROR = "NameError: name 'quantity' is not defined. Did you mean: 'quantities'?"

QUICK_LOOK = ("A short Python script, `budget.py`, that adds up prices × quantities. It "
              "crashes: line 4 uses `quantity`, but the parameter is called `quantities`.")
REVIEW = ("**Bug:** line 4 refers to `quantity`; the parameter is `quantities`.\n\n"
          "```python\nfor price, qty in zip(prices, quantities):\n    total += price * qty\n"
          "```\n\n**Also:** `total` is both the function's name and a variable inside it. It "
          "works, but renaming the variable avoids confusion.")


def screenshot() -> Image.Image:
    image = Image.new("RGB", (1280, 760), (30, 32, 38))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1280, 36), fill=(44, 47, 56))
    draw.text((16, 10), "budget.py - Code", fill=(210, 210, 210))
    for index, line in enumerate(CODE):
        draw.text((40, 70 + index * 30), f"{index + 1:>2}  {line}", fill=(220, 220, 200))
    draw.rectangle((0, 560, 1280, 760), fill=(24, 24, 28))
    draw.text((24, 580), "TERMINAL", fill=(150, 150, 150))
    draw.text((24, 620), "Traceback (most recent call last):", fill=(230, 120, 120))
    draw.text((24, 650), ERROR, fill=(230, 120, 120))
    return image


def shot() -> Shot:
    small = imaging.downscale(imaging.trim(screenshot()))
    return Shot(imaging.jpeg(small), small.size, imaging.fingerprint(small), 1,
                "budget.py - Code", "window")


def exchanges() -> list[Exchange]:
    picture = shot()
    return [Exchange("", QUICK_LOOK, picture),
            Exchange("Review", REVIEW, picture, "review", follow_up=True)]
