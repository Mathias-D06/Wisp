"""Dev helper: a made-up Files & Share tab for screenshots and recordings (D-051).

Points the tab at a temporary folder of invented files (pictures drawn here), a few generic app
names, and a stand-in phone link with a made-up private address. Nothing from this PC's own
Recent items, Downloads, apps or network is read or shown, and no server is started.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, Signal

from wisp.files.finder import FileFinder
from wisp.phone.server import Upload
from wisp.system.app_index import AppEntry

DOCUMENTS = ["Quarterly report.docx", "Budget 2026.xlsx", "Trip itinerary.pdf",
             "Reading list.txt", "Report draft v2.docx"]
DOWNLOADS = ["invoice-0912.pdf", "holiday-photo.jpg", "setup-notes.txt", "mountain-lake.png",
             "slides-final.pptx"]
APPS = ["Calculator", "Notepad", "Paint", "Photos", "Clock"]


def _picture(path: Path, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (160, 120))
    for y in range(120):
        t = y / 119
        row = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        for x in range(160):
            image.putpixel((x, y), row)
    image.save(path)


def make_files() -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="wisp-sample-files-"))
    documents, downloads = root / "Documents", root / "Downloads"
    documents.mkdir()
    downloads.mkdir()
    now = time.time()
    for index, name in enumerate(DOCUMENTS):
        (documents / name).write_text("A made-up file for Wisp's screenshots.", encoding="utf-8")
        os.utime(documents / name, (now - 3600 * (index * 7 + 1),) * 2)
    for index, name in enumerate(DOWNLOADS):
        path = downloads / name
        if name.endswith((".jpg", ".png")):
            _picture(path, (238, 154, 92) if index == 1 else (96, 160, 214),
                     (120, 70, 140) if index == 1 else (40, 90, 70))
        else:
            path.write_text("A made-up download.", encoding="utf-8")
        os.utime(path, (now - 600 * (index * 3 + 1),) * 2)
    return documents, downloads


class SampleApps:
    def __init__(self) -> None:
        self.entries = [AppEntry(i, name, f"{name}.exe", "path", 0, False)
                        for i, name in enumerate(APPS, start=1)]

    def all(self) -> list[AppEntry]:
        return list(self.entries)

    def launch(self, entry) -> None:
        pass

    def set_pinned(self, entry_id: int, pinned: bool) -> None:
        pass


class SamplePhone(QObject):
    """Looks like a running phone link; serves nothing."""

    changed = Signal()

    def __init__(self, wall) -> None:
        super().__init__()
        self._wall = wall
        self.running = False
        self.error = ""
        self.network = "Home Wi-Fi"
        self.url = "http://192.168.1.20:52114/" + "Kq3VzR8tW2mY7pLx4nHc9dFb6jSg1aEo5uTiZrNwXy0/"
        self.waiting: list[Upload] = []
        self.ends_at = 0.0
        self._offers: list[Path] = []

    def start(self, paths=None) -> bool:
        self.running = True
        self._offers += list(paths or [])
        self.ends_at = self._wall() + 581
        self.changed.emit()
        return True

    def stop(self) -> None:
        self.running = False
        self.waiting = []
        self.ends_at = 0.0
        self.changed.emit()

    def offers(self) -> list[Path]:
        return list(self._offers)

    def remaining_s(self) -> float:
        return max(0.0, self.ends_at - self._wall())

    def ask(self, name: str, size: int) -> None:
        self.waiting.append(Upload(len(self.waiting) + 1, name, size, "192.168.1.31"))
        self.changed.emit()

    def accept(self, upload) -> None:
        self.waiting.remove(upload)
        self.changed.emit()

    decline = accept


def install(wisp_app, wall=time.time):
    """Swap the Files & Share tab's data for made-up files; returns (tab, phone, files)."""
    tab = dict(wisp_app.island.panel.tabs)["Files & Share"]
    documents, downloads = make_files()
    everything = [(p, p.stat().st_mtime) for folder in (documents, downloads)
                  for p in folder.iterdir()]

    def index(sql: str) -> list[tuple[Path, float]]:
        terms = [part.split("%")[0] for part in sql.split("LIKE '%")[1:]]
        return [(p, m) for p, m in everything if all(t.lower() in p.name.lower() for t in terms)]

    finder = FileFinder([documents.parent], index=index, downloads_folder=downloads)
    finder.recent = lambda limit=12: _recent(documents)[:limit]
    tab.finder = finder
    tab.apps = SampleApps()
    phone = SamplePhone(wall)
    phone.changed.connect(tab._update_phone)
    phone.changed.connect(lambda: wisp_app.island.machine.set_sharing(
        "Phone link" if phone.running else None, phone.ends_at if phone.running else None))
    tab.phone = phone
    tab.shelf.clear()
    tab.shelf.add([downloads / "holiday-photo.jpg", documents / "Quarterly report.docx"])
    tab.refresh()
    return tab, phone, (documents, downloads)


def _recent(documents: Path):
    from wisp.files.finder import FileResult

    files = sorted(documents.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    return [FileResult(p, p.stat().st_mtime) for p in files]
