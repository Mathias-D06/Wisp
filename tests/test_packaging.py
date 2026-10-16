"""Packaging (phase 10): version, self-check, notices, and the installer agreeing with the app."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"


def test_version_matches_pyproject():
    from wisp import __version__

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == __version__
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)  # the spec turns it into a file version


def test_version_flag():
    result = subprocess.run([sys.executable, "-m", "wisp", "--version"], capture_output=True,
                            text=True, timeout=60)
    from wisp import __version__

    assert result.returncode == 0 and result.stdout.strip() == __version__


@pytest.mark.windows
def test_self_check_from_source(tmp_path):
    report = tmp_path / "report.json"
    result = subprocess.run([sys.executable, "-m", "wisp", "--self-check", str(report)],
                            capture_output=True, text=True, timeout=300, cwd=tmp_path)
    data = json.loads(report.read_text(encoding="utf-8"))
    failed = [c for c in data["checks"] if c["required"] and not c["ok"]]
    assert result.returncode == 0 and data["ok"], failed
    assert {c["check"] for c in data["checks"]} >= {"modules", "qt", "sqlite_fts5", "dpapi",
                                                     "portaudio", "winrt", "uia", "scheduler",
                                                     "screen_assist", "gemini_config"}
    assert data["frozen"] is False


def test_self_check_reports_failures(monkeypatch, tmp_path, capsys):
    from wisp import selfcheck

    def broken() -> str:
        raise RuntimeError("missing DLL")

    monkeypatch.setattr(selfcheck, "CHECKS", [("required_part", True, broken),
                                              ("optional_part", False, broken),
                                              ("fine", True, lambda: "ok")])
    monkeypatch.setenv("WISP_DATA_DIR", str(tmp_path / "unused"))
    report = tmp_path / "r.json"
    assert selfcheck.run(report) == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    assert [(c["check"], c["ok"]) for c in data["checks"]] == [
        ("required_part", False), ("optional_part", False), ("fine", True)]
    monkeypatch.setattr(selfcheck, "CHECKS", [("optional_part", False, broken)])
    assert selfcheck.run(report) == 0  # optional failures don't fail the build
    capsys.readouterr()


def test_notices_cover_runtime_dependencies_only():
    sys.path.insert(0, str(PACKAGING))
    try:
        import notices
    finally:
        sys.path.remove(str(PACKAGING))
    names = {re.sub(r"[-_.]+", "-", d.metadata["Name"]).lower()
             for d in notices.runtime_closure("wisp")}
    assert {"pyside6-essentials", "shiboken6", "google-genai", "apscheduler", "comtypes",
            "sounddevice", "numpy", "pillow", "pywin32", "winrt-runtime"} <= names
    assert not names & {"pytest", "ruff", "pyinstaller", "pytest-qt"}


def test_notices_carry_the_icon_licence(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(PACKAGING))
    try:
        import notices
    finally:
        sys.path.remove(str(PACKAGING))
    out = tmp_path / "THIRD_PARTY_NOTICES.txt"
    monkeypatch.setattr(sys, "argv", ["notices.py", str(out)])
    notices.main()
    text = out.read_text(encoding="utf-8")
    assert "Lucide icons 1.56.0" in text and "ISC License" in text
    assert "Permission to use, copy, modify" in text  # the full ISC notice, not just its name
    capsys.readouterr()


def test_installer_agrees_with_the_app():
    from wisp import single_instance, startup

    script = (PACKAGING / "installer.iss").read_text(encoding="utf-8")
    assert f"AppMutex={single_instance.MUTEX_NAME}" in script
    assert f'ValueName: "{startup.VALUE_NAME}"' in script
    assert startup.RUN_KEY in script
    assert '--background' in script  # same command line as paths.launch_command() when frozen
    assert "PrivilegesRequired=lowest" in script
    # Silent uninstall must keep user data (the question defaults to "no").
    assert "MB_DEFBUTTON2, IDNO" in script


def test_spec_inputs_exist():
    spec = (PACKAGING / "wisp.spec").read_text(encoding="utf-8")
    for name in ("launcher.py", "wisp.ico"):
        assert name in spec and (PACKAGING / name).is_file()
    assert "console=False" in spec and "collect_submodules(\"comtypes.gen\")" in spec
