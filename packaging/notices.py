"""Write THIRD_PARTY_NOTICES.txt for the bundle: every runtime package Wisp ships (Wisp's
dependencies and theirs, read from the installed package metadata) with version, licence and
home page, plus the LGPL note for Qt/PySide6.

Run: .venv\\Scripts\\python packaging\\notices.py [output path]
"""

from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "THIRD_PARTY_NOTICES.txt"

HEADER = """Wisp — third-party software
================================

Wisp bundles the Python runtime (PSF License) and the packages below, unmodified. Licence
texts are available from each project's home page and its package on PyPI.

Qt for Python (PySide6, shiboken6) and the Qt libraries are used under the GNU Lesser General
Public License v3. They are shipped as separate, replaceable DLLs and Python extension modules
in the installation folder (PyInstaller "onedir" layout), so you can replace them with your own
build of the same version. Source code: https://code.qt.io/cgit/pyside/pyside-setup.git/ and
https://download.qt.io/official_releases/QtForPython/ .

"""


def _requirement_names(dist: metadata.Distribution) -> list[str]:
    names = []
    for requirement in dist.requires or []:
        if "extra ==" in requirement:
            continue  # optional extras are not installed with Wisp
        marker = requirement.split(";", 1)[1] if ";" in requirement else ""
        if "sys_platform" in marker and "win32" not in marker and "!=" not in marker:
            continue
        name = re.split(r"[\s<>=!~;\[(]", requirement, maxsplit=1)[0]
        names.append(name)
    return names


def runtime_closure(root: str) -> list[metadata.Distribution]:
    seen: dict[str, metadata.Distribution] = {}
    pending = _requirement_names(metadata.distribution(root))
    while pending:
        name = pending.pop()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue  # requirement for another platform / Python version
        seen[key] = dist
        pending.extend(_requirement_names(dist))
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def licence(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or []
                   if c.startswith("License ::")]
    if classifiers:
        return "; ".join(classifiers)
    text = (meta.get("License") or "").strip().splitlines()
    return text[0][:80] if text else "see project page"


def home(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    if meta.get("Home-page"):
        return meta["Home-page"]
    for url in meta.get_all("Project-URL") or []:
        label, _, link = url.partition(",")
        if label.strip().lower() in ("homepage", "home", "source", "repository", "source code"):
            return link.strip()
    return f"https://pypi.org/project/{meta['Name']}/"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [HEADER]
    for dist in runtime_closure("wisp"):
        meta = dist.metadata
        lines.append(f"{meta['Name']} {dist.version}\n  Licence: {licence(dist)}\n"
                     f"  {home(dist)}\n")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(lines) - 1} packages)")


if __name__ == "__main__":
    main()
