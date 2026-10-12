"""File basics: open, recent files, search, delete to the Recycle Bin only.

Sources: os.startfile (docs.python.org, ShellExecute "open"); SHFILEOPSTRUCTW (FO_DELETE with
FOF_ALLOWUNDO needs a fully qualified path to recycle; FOF_WANTNUKEWARNING warns before any
permanent delete); Recent Items folder = %APPDATA%\\Microsoft\\Windows\\Recent (FOLDERID_Recent).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

EXECUTABLE_SUFFIXES = {
    ".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".msi", ".msp", ".scr", ".lnk", ".url", ".reg", ".jar", ".hta", ".cpl", ".pif", ".appref-ms",
}

FO_DELETE = 0x0003
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
FOF_WANTNUKEWARNING = 0x4000


def known_folders() -> dict[str, Path]:
    home = Path.home()
    folders = {
        "home": home,
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "downloads": home / "Downloads",
        "pictures": home / "Pictures",
        "music": home / "Music",
        "videos": home / "Videos",
    }
    try:
        from win32com.shell import shell, shellcon

        for key, csidl in (("desktop", shellcon.CSIDL_DESKTOPDIRECTORY),
                           ("documents", shellcon.CSIDL_PERSONAL),
                           ("pictures", shellcon.CSIDL_MYPICTURES),
                           ("music", shellcon.CSIDL_MYMUSIC),
                           ("videos", shellcon.CSIDL_MYVIDEO)):
            folders[key] = Path(shell.SHGetFolderPath(0, csidl, None, 0))
    except Exception:  # redirected folders unavailable: keep the profile defaults
        folders.setdefault("documents", home / "Documents")
    return folders


def resolve_path(text: str) -> Path:
    """Expand env vars, ~ and known folder names ("downloads") into a full path."""
    raw = os.path.expandvars(os.path.expanduser(text.strip().strip('"')))
    folders = known_folders()
    key = raw.lower().rstrip("\\/")
    if key in folders:
        return folders[key]
    first, _, rest = raw.replace("/", "\\").partition("\\")
    if first.lower() in folders and rest:
        return folders[first.lower()] / rest
    return Path(raw)


def is_executable(path: Path) -> bool:
    return path.suffix.lower() in EXECUTABLE_SUFFIXES


def open_path(path: Path) -> None:
    os.startfile(str(path))  # ShellExecute "open" with the default app


def reveal(path: Path) -> None:
    import subprocess

    subprocess.Popen(["explorer.exe", "/select,", str(path)])


@dataclass
class FileHit:
    path: Path
    modified: float

    def as_dict(self) -> dict:
        return {"name": self.path.name, "path": str(self.path),
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.modified))}


def _resolve_shortcut(lnk: Path) -> Path | None:
    try:
        import pythoncom
        from win32com.shell import shell

        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                          pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(lnk))
        target, _ = link.GetPath(0)
        return Path(target) if target else None
    except Exception:
        return None


def recent_files(query: str | None = None, limit: int = 15) -> list[FileHit]:
    recent = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"
    if not recent.is_dir():
        return []
    shortcuts = sorted(recent.glob("*.lnk"), key=lambda p: p.stat().st_mtime, reverse=True)
    hits: list[FileHit] = []
    for lnk in shortcuts[:400]:
        target = _resolve_shortcut(lnk)
        if target is None or not target.exists() or target.is_dir():
            continue
        if query and fuzz.partial_ratio(query.lower(), target.name.lower()) < 75:
            continue
        hits.append(FileHit(target, lnk.stat().st_mtime))
        if len(hits) >= limit:
            break
    return hits


def search_files(query: str, roots: list[Path] | None = None, limit: int = 15,
                 time_budget_s: float = 4.0, max_depth: int = 6) -> list[FileHit]:
    folders = known_folders()
    roots = roots or [folders[k] for k in ("desktop", "documents", "downloads", "pictures",
                                           "music", "videos") if folders[k].is_dir()]
    deadline = time.monotonic() + time_budget_s
    scored: list[tuple[float, FileHit]] = []
    needle = query.lower()
    for root in roots:
        base_depth = len(root.parts)
        for current, dirs, files in os.walk(root):
            if time.monotonic() > deadline:
                break
            if len(Path(current).parts) - base_depth >= max_depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith((".", "$")) and d != "node_modules"]
            for name in files + dirs:
                score = fuzz.partial_ratio(needle, name.lower())
                if score >= 80:
                    full = Path(current) / name
                    try:
                        scored.append((score, FileHit(full, full.stat().st_mtime)))
                    except OSError:
                        continue
    scored.sort(key=lambda pair: (pair[0], pair[1].modified), reverse=True)
    return [hit for _, hit in scored[:limit]]


def protected_reason(path: Path) -> str | None:
    """Why a path must never be deleted by Wisp, or None if it is an ordinary user item."""
    try:
        full = path.resolve()
    except OSError:
        return "That path can't be resolved."
    if not full.is_absolute():
        return "A full path is needed so the item goes to the Recycle Bin."
    if str(full).startswith("\\\\"):
        return "Network locations have no Recycle Bin, so Wisp won't delete there."
    if full.parent == full:
        return "Wisp won't delete a whole drive."
    system_roots = [os.environ.get(v, "") for v in ("SystemRoot", "ProgramFiles",
                                                    "ProgramFiles(x86)", "ProgramData")]
    for root in filter(None, system_roots):
        try:
            if full == Path(root) or Path(root) in full.parents:
                return "That's a Windows or program folder; Wisp won't delete there."
        except OSError:
            continue
    if full == Path.home() or full in known_folders().values():
        return "That's one of your main folders; Wisp won't delete it."
    if not full.exists():
        return f"{full} doesn't exist."
    return None


def recycle(path: Path) -> None:
    """Move to the Recycle Bin. Windows warns before any permanent delete (FOF_WANTNUKEWARNING)."""
    from win32com.shell import shell

    full = str(path.resolve())
    flags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_WANTNUKEWARNING
    result, aborted = shell.SHFileOperation((0, FO_DELETE, full, None, flags, None, None))
    if result != 0:
        raise OSError(f"Windows could not recycle the item (code {result}).")
    if aborted:
        raise OSError("The delete was cancelled.")
