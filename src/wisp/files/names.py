"""Safe file names (Microsoft, "Naming Files, Paths, and Namespaces").

``sanitize`` turns any name a phone (or a person) sends into one plain file name inside the
target folder: only the last path component is kept, reserved characters and control characters
are removed, reserved device names (CON, NUL.txt, COM¹ …) get a leading underscore, and the name
can't end with a space or a period. ``unique`` never overwrites: "name (2).ext", "name (3).ext"…
"""

from __future__ import annotations

import re
from pathlib import Path

RESERVED_CHARS = '<>:"/\\|?*'
DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL",
                *(f"COM{d}" for d in "123456789¹²³"), *(f"LPT{d}" for d in "123456789¹²³")}
MAX_NAME = 180  # well inside 255 per component and MAX_PATH with Downloads\Wisp in front
FALLBACK = "file"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def sanitize(name: str, fallback: str = FALLBACK) -> str:
    """One safe file name from untrusted text (never a path)."""
    last = re.split(r"[\\/]", name or "")[-1]
    cleaned = _CONTROL.sub("", last)
    cleaned = "".join(ch for ch in cleaned if ch not in RESERVED_CHARS)
    cleaned = cleaned.strip().rstrip(". ")
    if cleaned in ("", ".", ".."):
        return fallback
    if cleaned.partition(".")[0].strip().upper() in DEVICE_NAMES:  # NUL and NUL.txt: the device
        cleaned = "_" + cleaned
    if len(cleaned) > MAX_NAME:
        path = Path(cleaned)
        keep = path.suffix if len(path.suffix) <= 16 else ""
        cleaned = cleaned[: MAX_NAME - len(keep)].rstrip(". ") + keep
    return cleaned or fallback


def unique(folder: Path, name: str) -> Path:
    """``folder / name``, or the first free "name (n).ext" if that exists."""
    candidate = folder / name
    if not candidate.exists():
        return candidate
    path = Path(name)
    stem, suffix = path.stem, path.suffix
    for number in range(2, 10_000):
        candidate = folder / f"{stem} ({number}){suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Too many files called {name} in {folder}.")


def valid_new_name(name: str) -> str | None:
    """Why ``name`` can't be used to rename a file, or None if it can (no silent changes:
    renaming tells the person what's wrong instead)."""
    if not name or not name.strip():
        return "The name can't be empty."
    if any(ch in RESERVED_CHARS for ch in name) or _CONTROL.search(name):
        return 'A name can\'t contain \\ / : * ? " < > |.'
    if name != name.rstrip(". "):
        return "A name can't end with a space or a period."
    if name.partition(".")[0].strip().upper() in DEVICE_NAMES:
        return f"{name.partition('.')[0]} is reserved by Windows."
    if len(name) > 240:
        return "That name is too long."
    return None
