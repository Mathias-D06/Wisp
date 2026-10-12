"""F2 tools: URL building, path rules, risk escalation."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from wisp.settings import SettingsStore
from wisp.tools.base import Risk, ToolContext, ToolError
from wisp.tools.builtin import files as files_tools
from wisp.tools.builtin import ui as ui_tools
from wisp.tools.builtin import web as web_tools
from wisp.winapi import files as fs


def test_search_urls():
    assert web_tools.search_url("youtube", "lofi beats") == (
        "https://www.youtube.com/results?search_query=lofi+beats")
    assert web_tools.search_url("google", "a&b") == "https://www.google.com/search?q=a%26b"
    assert web_tools.search_url("amazon", "gift wrap", "www.amazon.co.uk") == (
        "https://www.amazon.co.uk/s?k=gift+wrap")


def test_web_search_opens_default_browser(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(web_tools.webbrowser, "open", opened.append)
    ctx = ToolContext("voice", SimpleNamespace(settings=SettingsStore(tmp_path / "s.json")))
    result = web_tools.web_search(ctx, {"query": "lofi beats", "site": "youtube"})
    assert opened == [result["opened"]] and "lofi+beats" in opened[0]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///C:/Windows", "ftp://x.org"])
def test_open_url_rejects_non_web(url, monkeypatch):
    monkeypatch.setattr(web_tools.webbrowser, "open", lambda u: None)
    with pytest.raises(ToolError):
        web_tools.open_url(ToolContext("voice", None), {"url": url})


def test_open_url_adds_https(monkeypatch):
    opened = []
    monkeypatch.setattr(web_tools.webbrowser, "open", opened.append)
    web_tools.open_url(ToolContext("voice", None), {"url": "example.org/page"})
    assert opened == ["https://example.org/page"]


def test_risky_click_names():
    for name in ("Send", "Place order", "Buy now", "Delete", "OK", "Sign out", "Allow"):
        assert ui_tools.is_risky_name(name), name
    for name in ("Settings", "Sending options help", "Home", "Search", "Okapi"):
        assert not ui_tools.is_risky_name(name), name
    assert ui_tools._click_risk({"name": "Submit"}) == Risk.CONFIRM
    assert ui_tools._click_risk({"name": "Settings"}) == Risk.SAFE
    assert ui_tools._type_risk({"text": "hi", "submit": True}) == Risk.CONFIRM
    assert ui_tools._type_risk({"text": "hi"}) == Risk.SAFE


def test_resolve_known_folders():
    downloads = fs.resolve_path("downloads")
    assert downloads.name.lower() == "downloads" or downloads.exists()
    assert fs.resolve_path("%USERPROFILE%") == Path(os.environ["USERPROFILE"])
    assert fs.resolve_path("documents\\notes.txt").name == "notes.txt"


def test_executables_need_confirmation():
    assert files_tools._open_risk({"path": "C:/tools/setup.exe"}) == Risk.CONFIRM
    assert files_tools._open_risk({"path": "C:/x/run.ps1"}) == Risk.CONFIRM
    assert files_tools._open_risk({"path": "C:/x/report.pdf"}) == Risk.SAFE


def test_protected_paths(tmp_path):
    assert "drive" in fs.protected_reason(Path("C:\\"))
    assert "Windows" in fs.protected_reason(Path(os.environ["SYSTEMROOT"]) / "System32")
    assert "main folders" in fs.protected_reason(Path.home())
    assert "doesn't exist" in fs.protected_reason(tmp_path / "missing.txt")
    assert "Network" in fs.protected_reason(Path("\\\\server\\share\\x.txt"))
    target = tmp_path / "ok.txt"
    target.write_text("x")
    assert fs.protected_reason(target) is None


def test_delete_tool_refuses_protected(monkeypatch):
    called = []
    monkeypatch.setattr(fs, "recycle", called.append)
    with pytest.raises(ToolError):
        files_tools.delete_to_recycle_bin(ToolContext("voice", None), {"path": "C:\\"})
    assert called == []


def test_delete_tool_metadata():
    tool = next(t for t in files_tools.tools() if t.name == "delete_to_recycle_bin")
    assert tool.risk == Risk.CONFIRM


@pytest.mark.windows
@pytest.mark.skipif(os.environ.get("WISP_RECYCLE_TEST") != "1",
                    reason="opt-in: leaves a probe file in the Recycle Bin")
def test_real_recycle(tmp_path):
    probe = tmp_path / "wisp-pytest-recycle-probe.txt"
    probe.write_text("probe")
    fs.recycle(probe)
    assert not probe.exists()
    import win32com.client

    bin_folder = win32com.client.Dispatch("Shell.Application").NameSpace(10)  # ssfBITBUCKET
    names = [item.Name for item in bin_folder.Items()]
    assert any(name.startswith("wisp-pytest-recycle-probe") for name in names)


@pytest.mark.windows
def test_recent_and_search_do_not_crash(tmp_path):
    (tmp_path / "quarterly-report.txt").write_text("x")
    hits = fs.search_files("quarterly", [tmp_path])
    assert hits and hits[0].path.name == "quarterly-report.txt"
    assert isinstance(fs.recent_files(limit=3), list)
