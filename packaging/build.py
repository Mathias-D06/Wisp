"""Build Wisp: icon → third-party notices → PyInstaller (dist\\Wisp\\Wisp.exe) → self-check of
the built exe → Inno Setup installer (dist\\WispSetup-<version>.exe) when ISCC is available.

Run: .venv\\Scripts\\python packaging\\build.py [--no-installer]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "src"))


def step(title: str) -> None:
    print(f"\n=== {title}", flush=True)


def run(args: list[str], **kwargs) -> None:
    print(">", " ".join(args), flush=True)
    subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def find_iscc() -> str | None:
    candidates = [
        os.environ.get("ISCC", ""),
        shutil.which("ISCC") or "",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"),
        str(Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Inno Setup 6" / "ISCC.exe"),
        str(Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Inno Setup 6"
            / "ISCC.exe"),
    ]
    return next((c for c in candidates if c and Path(c).is_file()), None)


def self_check(exe: Path) -> None:
    report = Path(tempfile.mkdtemp(prefix="wisp-build-")) / "self-check.json"
    result = subprocess.run([str(exe), "--self-check", str(report)], timeout=300)
    data = json.loads(report.read_text(encoding="utf-8"))
    for item in data["checks"]:
        mark = "ok " if item["ok"] else ("ERR" if item["required"] else "-- ")
        print(f"  {mark} {item['check']:<14} {item['detail'].splitlines()[0][:110]}")
    if result.returncode != 0 or not data["ok"] or not data["frozen"]:
        raise SystemExit("Self-check of the built exe failed.")


def main() -> None:
    from wisp import __version__

    python = sys.executable
    step("Icon and notices")
    run([python, str(PACKAGING / "make_icon.py")])
    run([python, str(PACKAGING / "notices.py")])

    step("Generate the UI Automation and Network List wrappers (comtypes)")
    run([python, "-c", "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll');"
         " from comtypes.gen import UIAutomationClient; print(UIAutomationClient.__file__)"])
    run([python, "-c", "import comtypes.client; from wisp.phone.network import "
         "NETWORK_LIST_LIBRARY as lib; print(comtypes.client.GetModule(lib).__file__)"])

    step(f"PyInstaller (Wisp {__version__})")
    run([python, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(DIST), "--workpath", str(ROOT / "build" / "pyinstaller"),
         str(PACKAGING / "wisp.spec")])
    exe = DIST / "Wisp" / "Wisp.exe"
    size = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file())
    print(f"built {exe} ({size / 1e6:.0f} MB folder)")

    step("Self-check of the built exe")
    self_check(exe)

    if "--no-installer" in sys.argv:
        return
    step("Installer")
    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup (ISCC.exe) not found; skipping the installer.")
        return
    run([iscc, f"/DAppVersion={__version__}", f"/DSourceDir={DIST / 'Wisp'}",
         f"/O{DIST}", str(PACKAGING / "installer.iss")])
    print(f"built {DIST / f'WispSetup-{__version__}.exe'}")


if __name__ == "__main__":
    main()
