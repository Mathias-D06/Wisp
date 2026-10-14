"""D-051: Files & Share without the UI: safe file names, the shelf (kept across restarts), file
actions (rename, move, copy, and delete only ever to the Recycle Bin), file search (the Windows
Search SQL Wisp builds, fuzzy ranking, the fallback), Downloads, and which file "this" means."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from wisp.db import Database
from wisp.files import actions, names
from wisp.files.finder import FileFinder, index_sql, like_literal, rank, string_literal
from wisp.files.resolve import NotFound, resolve
from wisp.files.shelf import MAX_ITEMS, Shelf


# ----- file names from a phone -------------------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("holiday.jpg", "holiday.jpg"),
    ("../../evil.txt", "evil.txt"),
    ("..\\..\\Windows\\System32\\evil.dll", "evil.dll"),
    ("C:\\Users\\me\\AppData\\Roaming\\run.bat", "run.bat"),
    ("/etc/passwd", "passwd"),
    ("a<b>c:d\"e|f?g*h.txt", "abcdefgh.txt"),
    ("bell\x07and\x00nul\x1f.txt", "bellandnul.txt"),
    ("CON", "_CON"), ("nul.txt", "_nul.txt"), ("Com1.tar.gz", "_Com1.tar.gz"),
    ("LPT³", "_LPT³"), ("console.txt", "console.txt"),
    ("report. . .", "report"), ("  spaced  ", "spaced"),
    ("", "file"), ("..", "file"), ("///", "file"), ("\\\\server\\share\\", "file"),
])
def test_names_from_a_phone_become_one_safe_file_name(raw, expected):
    assert names.sanitize(raw) == expected


def test_long_names_are_cut_but_keep_their_extension():
    name = names.sanitize("x" * 400 + ".jpeg")
    assert len(name) <= names.MAX_NAME and name.endswith(".jpeg")


def test_received_files_never_overwrite(tmp_path):
    (tmp_path / "photo.jpg").write_text("1")
    (tmp_path / "photo (2).jpg").write_text("2")
    assert names.unique(tmp_path, "photo.jpg") == tmp_path / "photo (3).jpg"
    assert names.unique(tmp_path, "new.txt") == tmp_path / "new.txt"


def test_rename_rejects_names_windows_refuses():
    assert names.valid_new_name("Report final.docx") is None
    for bad in ("", "  ", "a/b", "what?", "trailing.", "trailing ", "NUL.txt", "x" * 241):
        assert names.valid_new_name(bad)


# ----- the shelf ----------------------------------------------------------------------------------
def test_shelf_keeps_files_across_restarts_newest_first(tmp_path):
    a, b, c = (tmp_path / n for n in ("a.txt", "b.png", "folder"))
    a.write_text("a")
    b.write_bytes(b"b")
    c.mkdir()
    clock = iter(range(100, 200)).__next__
    shelf = Shelf(Database(tmp_path / "wisp.sqlite3"), clock=clock)
    assert shelf.add([a, tmp_path / "missing.txt"]) == [a]  # missing paths are skipped
    shelf.add([b, c])
    shelf.add([a])  # already there: moves to the front
    reopened = Shelf(Database(tmp_path / "wisp.sqlite3"))
    assert [item.path for item in reopened.items()] == [a, c, b]
    b.unlink()
    assert [item.exists for item in reopened.items()] == [True, True, False]
    assert reopened.newest().path == a
    assert reopened.forget_missing() == 1 and len(reopened.items()) == 2
    renamed = tmp_path / "a2.txt"
    a.rename(renamed)
    reopened.renamed(a, renamed)
    assert reopened.items()[0].path == renamed
    assert reopened.remove(renamed) and not reopened.remove(renamed)


def test_shelf_holds_the_newest_fifty(tmp_path):
    clock = iter(range(1000)).__next__
    shelf = Shelf(Database(":memory:"), clock=clock)
    files = []
    for index in range(MAX_ITEMS + 5):
        path = tmp_path / f"f{index}.txt"
        path.write_text("x")
        files.append(path)
        shelf.add([path])
    items = shelf.items()
    assert len(items) == MAX_ITEMS and items[0].path == files[-1]


# ----- file actions ------------------------------------------------------------------------------
class FakeClipboard:
    def __init__(self):
        self.mime = self.text = None

    def setMimeData(self, mime):
        self.mime = mime

    def setText(self, text):
        self.text = text


def test_copy_puts_files_and_paths_on_the_clipboard(qtbot, tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("b")
    board = FakeClipboard()
    assert actions.copy_files([a, b, tmp_path / "gone.txt"], board) == 2
    assert [Path(url.toLocalFile()) for url in board.mime.urls()] == [a, b]
    assert actions.copy_path([a, b], board) == f"{a}\n{b}"
    with pytest.raises(actions.ActionError):
        actions.copy_files([tmp_path / "gone.txt"], board)


def test_rename_and_move_never_overwrite(tmp_path):
    source = tmp_path / "draft.txt"
    source.write_text("text")
    (tmp_path / "taken.txt").write_text("keep me")
    moved_events = []
    with pytest.raises(actions.ActionError, match="already"):
        actions.rename(source, "taken.txt")
    with pytest.raises(actions.ActionError, match="end with"):
        actions.rename(source, "bad.")
    renamed = actions.rename(source, "final.txt", lambda old, new: moved_events.append(new))
    assert renamed == tmp_path / "final.txt" and renamed.read_text() == "text"
    assert (tmp_path / "taken.txt").read_text() == "keep me" and moved_events == [renamed]
    folder = tmp_path / "Archive"
    folder.mkdir()
    (folder / "final.txt").write_text("other")
    with pytest.raises(actions.ActionError, match="already has"):
        actions.move(renamed, folder)
    (folder / "final.txt").unlink()
    moved = actions.move(renamed, folder)
    assert moved == folder / "final.txt" and not renamed.exists()
    with pytest.raises(actions.ActionError, match="into itself"):
        actions.move(folder, folder)


def test_deleting_only_ever_uses_the_recycle_bin(tmp_path, monkeypatch):
    target = tmp_path / "old notes.txt"
    target.write_text("x")
    recycled = []

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a permanent delete was attempted")

    for module, name in ((os, "remove"), (os, "unlink"), (os, "rmdir"), (shutil, "rmtree")):
        monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(Path, "unlink", forbidden)
    monkeypatch.setattr(Path, "rmdir", forbidden)
    actions.recycle(target, recycler=recycled.append)
    assert recycled == [target] and target.exists()  # the recycler did the move, nothing else
    with pytest.raises(actions.ActionError, match="main folders"):
        actions.recycle(Path.home(), recycler=recycled.append)
    with pytest.raises(actions.ActionError, match="Windows or program"):
        actions.recycle(Path(os.environ["SYSTEMROOT"]) / "notepad.exe", recycler=recycled.append)
    assert recycled == [target]


def test_the_default_recycler_is_the_recycle_bin():
    from wisp.winapi import files as fs

    assert actions.recycle.__defaults__ == (fs.recycle,)
    assert fs.FOF_ALLOWUNDO & 0x40  # SHFileOperation keeps it restorable


# ----- search ------------------------------------------------------------------------------------
def test_windows_search_sql_escapes_what_the_person_typed():
    assert string_literal("O'Brien") == "O''Brien"
    assert like_literal("100%_[draft]'") == "100[%][_][[]draft]''"
    sql = index_sql(["tax", "50%"], [Path("C:/Users/Sam O'Neil")], top=20)
    assert sql == ("SELECT TOP 20 System.ItemPathDisplay, System.DateModified FROM SystemIndex "
                   "WHERE (SCOPE='file:C:/Users/Sam O''Neil') AND System.FileName LIKE '%tax%' "
                   "AND System.FileName LIKE '%50[%]%' ORDER BY System.DateModified DESC")


def test_search_ranks_fuzzily_and_tolerates_typos(tmp_path):
    now = time.time()
    rows = [(tmp_path / "Quarterly report.docx", now - 86400 * 40),
            (tmp_path / "report-2025.pdf", now - 3600),
            (tmp_path / "holiday photos", now),
            (tmp_path / "desktop.ini", now)]
    seen = []

    def index(sql):
        seen.append(sql)
        return rows if "'%rep%'" in sql else []  # the exact query finds nothing for the typo

    finder = FileFinder([tmp_path], index=index)
    results = finder.search("reprot", 5)
    assert [r.name for r in results][:2] == ["report-2025.pdf", "Quarterly report.docx"]
    assert len(seen) == 2 and "'%reprot%'" in seen[0] and finder.used_index
    assert all(r.name != "desktop.ini" for r in rank("desktop", rows, 5))
    assert finder.search("a", 5) == []  # one letter: no query


def test_search_walks_the_folders_without_the_index(tmp_path, monkeypatch):
    from wisp.winapi import files as fs

    (tmp_path / "budget 2026.xlsx").write_text("x")

    def no_index(_sql):
        raise OSError("Windows Search is off")

    walked = []
    real = fs.search_files

    def walk(query, roots, limit, time_budget_s):
        walked.append(roots)
        return real(query, roots, limit=limit, time_budget_s=time_budget_s)

    monkeypatch.setattr(fs, "search_files", walk)
    finder = FileFinder([tmp_path], index=no_index)
    assert [r.name for r in finder.search("budget", 5)] == ["budget 2026.xlsx"]
    assert walked == [[tmp_path]] and not finder.used_index


def test_downloads_newest_first_without_partial_downloads(tmp_path):
    for index, name in enumerate(("old.zip", "setup.exe.crdownload", "movie.mp4.part",
                                  "desktop.ini", "new.pdf")):
        path = tmp_path / name
        path.write_text("x")
        os.utime(path, (1000 + index, 1000 + index))
    finder = FileFinder(index=lambda _sql: [], downloads_folder=tmp_path)
    assert [r.name for r in finder.downloads()] == ["new.pdf", "old.zip"]
    assert finder.latest_download().name == "new.pdf"
    assert FileFinder(downloads_folder=tmp_path / "none").latest_download() is None


# ----- which file a request means --------------------------------------------------------------
def test_which_file_this_and_latest_download_mean(tmp_path):
    shelf = Shelf(Database(":memory:"))
    selected, shelved, download = (tmp_path / n for n in ("sel.txt", "shelf.txt", "dl.pdf"))
    for path in (selected, shelved, download):
        path.write_text("x")
    finder = FileFinder([tmp_path], index=lambda _sql: [(download, time.time())],
                        downloads_folder=tmp_path)
    os.utime(download, (time.time() + 10, time.time() + 10))
    assert resolve("this", finder, shelf, lambda: [selected]) == [selected]
    with pytest.raises(NotFound, match="Select the file"):
        resolve("this", finder, shelf, lambda: [])
    shelf.add([shelved])
    assert resolve(None, finder, shelf, lambda: []) == [shelved]
    assert resolve("the file I just downloaded", finder, shelf) == [download]
    assert resolve("latest download", finder, shelf) == [download]
    assert resolve("shelf", finder, shelf) == [shelved]
    assert resolve(str(selected), finder, shelf) == [selected]
    assert resolve("dl", finder, shelf) == [download]  # a clear search match
    with pytest.raises(NotFound, match="couldn't find"):
        resolve("zzzz", FileFinder([tmp_path], index=lambda _s: []), shelf)
