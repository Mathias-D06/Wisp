"""What Wisp never looks at (D-052): the Screen Assist blocklist, applied to every capture
(Screen Assist, Watch mode, look_at_screen and Circle to Ask).

A window is blocked when its app (process name, without ".exe") is on the app list, or when its
title contains one of the title words: whole words, any case. Windows only expose the active
tab's title, so a browser is blocked while a matching page is in front. Private browsing windows
are recognised by the words their titles carry (Incognito, InPrivate, Private Browsing): a
heuristic from window titles, not a documented signal, so the list can be edited.

* The active window blocked: nothing is captured ("I don't look at that window").
* A whole-screen capture: every visible blocked window on it is painted over before the image
  leaves the PC.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from PIL import Image, ImageDraw

REFUSAL = "I don't look at that window."

DEFAULT_APPS = [
    # password managers
    "1Password", "Bitwarden", "KeePass", "KeePassXC", "Dashlane", "LastPass", "NordPass",
    "Keeper", "KeeperPasswordManager", "RoboForm", "Enpass", "ProtonPass", "Proton Pass",
    # Windows sign-in and credential prompts
    "CredentialUIBroker", "LogonUI", "consent",
]
DEFAULT_TITLES = [
    # private browsing (Chrome, Edge, Firefox, Brave, Opera, Tor)
    "Incognito", "InPrivate", "Private Browsing", "Private window", "Tor Browser",
    # banking and payments
    "bank", "banking", "online banking", "PayPal", "checkout", "payment", "card details",
    "Barclays", "HSBC", "Lloyds", "NatWest", "Santander", "Nationwide", "Halifax", "Monzo",
    "Starling", "Revolut", "Chase", "Wise", "Stripe", "Klarna", "Apple Pay", "Google Pay",
    # password pages and vaults
    "password", "passwords", "1Password", "Bitwarden", "LastPass",
]


@dataclass(frozen=True)
class Blocklist:
    apps: tuple[str, ...] = tuple(DEFAULT_APPS)
    titles: tuple[str, ...] = tuple(DEFAULT_TITLES)

    @classmethod
    def from_lists(cls, apps: Iterable[str], titles: Iterable[str]) -> Blocklist:
        return cls(tuple(a.strip() for a in apps if a.strip()),
                   tuple(t.strip() for t in titles if t.strip()))

    def reason(self, process: str, title: str) -> str | None:
        """Why a window with this app and title is blocked, or None."""
        app = (process or "").removesuffix(".exe").casefold()
        for name in self.apps:
            if app == name.removesuffix(".exe").casefold():
                return f"app {name}"
        for word in self.titles:
            if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", title or "", re.IGNORECASE):
                return f"title word “{word}”"
        return None

    def blocks(self, window) -> bool:
        return self.reason(window.process, window.title) is not None


def intersect(a: tuple[int, int, int, int], b: tuple[int, int, int, int]
              ) -> tuple[int, int, int, int] | None:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    return (left, top, right, bottom) if right > left and bottom > top else None


def mask(image: Image.Image, region: tuple[int, int, int, int],
         hidden: Iterable[tuple[int, int, int, int]]) -> tuple[Image.Image, int]:
    """Paint over ``hidden`` rectangles (screen coordinates) inside ``region``; returns the
    image and how many were painted. ``image`` covers ``region`` at any scale."""
    width, height = image.size
    scale_x = width / max(1, region[2] - region[0])
    scale_y = height / max(1, region[3] - region[1])
    draw = ImageDraw.Draw(image)
    painted = 0
    for rect in hidden:
        overlap = intersect(rect, region)
        if overlap is None:
            continue
        box = (int((overlap[0] - region[0]) * scale_x), int((overlap[1] - region[1]) * scale_y),
               int((overlap[2] - region[0]) * scale_x + 0.999),
               int((overlap[3] - region[1]) * scale_y + 0.999))
        draw.rectangle(box, fill=(32, 32, 32))
        painted += 1
    return image, painted
