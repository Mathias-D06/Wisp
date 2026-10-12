from __future__ import annotations

from types import SimpleNamespace

import pytest

from wisp.system.app_index import AppIndex, _keep, score
from wisp.tools.base import ToolContext, ToolError
from wisp.tools.builtin.apps import find_apps, open_app

APPS = [
    ("Spotify", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify", "aumid"),
    ("Unity Hub", r"C:\Program Files\Unity Hub\Unity Hub.exe", "path"),
    ("Microsoft Word", "Microsoft.Office.WINWORD.EXE.15", "aumid"),
    ("WordPad", "Microsoft.Windows.WordPad", "aumid"),
    ("Notepad", "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App", "aumid"),
    ("Visual Studio Code", "Microsoft.VisualStudioCode", "aumid"),
    ("Visual Studio 2022", "VisualStudio.17", "aumid"),
]


@pytest.fixture
def index(db, monkeypatch):
    idx = AppIndex(db)
    monkeypatch.setattr(AppIndex, "_apps_folder", staticmethod(lambda: list(APPS)))
    monkeypatch.setattr(AppIndex, "_start_menu_shortcuts", staticmethod(
        lambda: [("Spotify", r"C:\Users\x\Start Menu\Spotify.lnk", "path"),
                 ("Blender", r"C:\ProgramData\Start Menu\Blender.lnk", "path")]))
    launched = []
    monkeypatch.setattr(AppIndex, "launch", lambda self, entry: launched.append(entry.name))
    idx.launched = launched
    idx.refresh()
    return idx


def ctx(index):
    return ToolContext(origin="voice", services=SimpleNamespace(app_index=index))


def test_refresh_merges_sources_without_duplicates(index):
    names = [e.name for e in index.all()]
    assert names.count("Spotify") == 1 and "Blender" in names
    assert index.count() == len(APPS) + 1


def test_refresh_keeps_launch_counts(index, db):
    entry = next(e for e in index.all() if e.name == "Notepad")
    db.execute("UPDATE app_index SET launch_count = 5 WHERE id = ?", (entry.id,))
    index.refresh()
    assert next(e for e in index.all() if e.name == "Notepad").launch_count == 5


def test_open_app_exact_and_fuzzy(index):
    assert open_app(ctx(index), {"name": "spotify"}) == {"opened": "Spotify"}
    assert open_app(ctx(index), {"name": "spotfy"})["opened"] == "Spotify"
    assert open_app(ctx(index), {"name": "unity"})["opened"] == "Unity Hub"
    assert index.launched == ["Spotify", "Spotify", "Unity Hub"]


def test_open_app_ambiguous_asks(index):
    result = open_app(ctx(index), {"name": "visual studio"})
    assert result["ambiguous"] is True
    assert set(result["options"]) >= {"Visual Studio Code", "Visual Studio 2022"}
    assert index.launched == []


def test_open_app_unknown(index):
    with pytest.raises(ToolError, match="couldn't find"):
        open_app(ctx(index), {"name": "photoshop elements"})


def test_find_apps(index):
    assert "Microsoft Word" in find_apps(ctx(index), {"query": "word"})["apps"]


def test_scoring_and_filters():
    assert score("notepad", "Notepad") == 120
    assert score("word", "Microsoft Word") > score("word", "Notepad")
    assert score("note", "Notepad", launch_count=10) > score("note", "Notepad")
    assert not _keep("Uninstall Foo", r"C:\x\uninstall.exe")
    assert not _keep("Foo Documentation", r"C:\x\foo.chm")
    assert _keep("Foo", r"C:\x\foo.exe")


@pytest.mark.windows
def test_real_apps_folder_enumerates():
    import pythoncom

    pythoncom.CoInitialize()
    entries = AppIndex._apps_folder()
    assert len(entries) > 10
    assert all(kind in ("aumid", "path") for _, _, kind in entries)
