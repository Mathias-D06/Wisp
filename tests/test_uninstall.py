"""D-061: uninstalling from inside Wisp. The installed copy's uninstaller is found next to
Wisp.exe; a detached ``Wisp.exe --run-uninstaller <pid>`` waits for Wisp to close (the
uninstaller refuses while Wisp's mutex exists) and then starts it. Fake files and fake process
launchers only: no test ever starts a real uninstaller."""

from __future__ import annotations

import subprocess
import sys

import pytest

from wisp import uninstall


def fake_install(tmp_path, *names):
    folder = tmp_path / "Programs" / "Wisp"
    folder.mkdir(parents=True)
    (folder / "Wisp.exe").write_bytes(b"MZ")
    for name in names:
        (folder / name).write_bytes(b"MZ")
    return folder


def test_the_uninstaller_is_found_only_in_an_installed_copy(tmp_path):
    folder = fake_install(tmp_path, "unins000.exe", "unins000.dat")
    exe = str(folder / "Wisp.exe")
    assert uninstall.uninstaller_path(exe, frozen=True) == folder / "unins000.exe"
    assert uninstall.uninstaller_path(exe, frozen=False) is None  # from source: never
    other = fake_install(tmp_path / "b", "unins001.exe")
    assert uninstall.uninstaller_path(str(other / "Wisp.exe"), frozen=True) == \
        other / "unins001.exe"
    bare = fake_install(tmp_path / "c")  # dist\Wisp, never installed
    assert uninstall.uninstaller_path(str(bare / "Wisp.exe"), frozen=True) is None
    assert uninstall.uninstaller_path() is None  # this test run is python.exe, not frozen


def test_the_waiter_is_this_exe_in_its_own_mode(tmp_path):
    started = []
    uninstall.start_waiter(4321, executable=r"C:\Wisp\Wisp.exe",
                           popen=lambda command, **kw: started.append((command, kw)))
    [(command, options)] = started
    assert command == [r"C:\Wisp\Wisp.exe", "--run-uninstaller", "4321"]
    assert options["creationflags"] & uninstall.DETACHED_PROCESS


def test_the_waiter_starts_the_uninstaller_only_after_wisp_closed(tmp_path):
    folder = fake_install(tmp_path, "unins000.exe")
    exe = str(folder / "Wisp.exe")
    started, waited = [], []

    def wait(pid):
        waited.append(pid)
        return True

    assert uninstall.run_uninstaller(77, exe, wait=wait,
                                     popen=lambda cmd, **kw: started.append(cmd)) == 0
    assert waited == [77] and started == [[str(folder / "unins000.exe")]]
    started.clear()
    assert uninstall.run_uninstaller(77, exe, wait=lambda pid: False,
                                     popen=lambda cmd, **kw: started.append(cmd)) == 3
    assert started == []  # Wisp still running: the uninstaller would only refuse
    bare = fake_install(tmp_path / "bare")
    assert uninstall.run_uninstaller(77, str(bare / "Wisp.exe"), wait=wait,
                                     popen=lambda cmd, **kw: started.append(cmd)) == 2
    assert started == []


@pytest.mark.windows
def test_waiting_for_a_process_to_exit():
    import os

    assert uninstall.wait_for_exit(os.getpid(), timeout_ms=50) is False  # still running
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    assert uninstall.wait_for_exit(child.pid, timeout_ms=30_000) is True
    child.wait()
    assert uninstall.wait_for_exit(child.pid, timeout_ms=50) is True  # already gone


def test_the_command_line_mode_never_runs_from_source():
    """``python -m wisp --run-uninstaller`` finds no uninstaller next to python.exe: exit 2."""
    result = subprocess.run([sys.executable, "-m", "wisp", "--run-uninstaller", "1"],
                            capture_output=True, timeout=60)
    assert result.returncode == 2


# ----- Settings → General ---------------------------------------------------------------------
@pytest.mark.qt
def test_settings_offers_uninstall_only_when_installed(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from wisp import startup
    from wisp.keystore import KeyStore
    from wisp.settings import SettingsStore
    from wisp.ui.settings.general_page import GeneralPage

    monkeypatch.setattr(startup, "is_enabled", lambda: False)
    store, keys = SettingsStore(tmp_path / "s.json"), KeyStore(tmp_path / "k.bin")
    calls = []
    source = GeneralPage(store, keys, uninstall_app=lambda: calls.append("uninstall"),
                         uninstaller=lambda: None)
    qtbot.addWidget(source)
    assert source.uninstall_button.isHidden()

    installed = GeneralPage(store, keys, uninstall_app=lambda: calls.append("uninstall"),
                            uninstaller=lambda: tmp_path / "unins000.exe")
    qtbot.addWidget(installed)
    assert not installed.uninstall_button.isHidden()
    answers = iter([QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes])
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kw: next(answers))
    installed.uninstall_button.click()
    assert calls == []  # Cancel: nothing happens
    installed.uninstall_button.click()
    assert calls == ["uninstall"]
