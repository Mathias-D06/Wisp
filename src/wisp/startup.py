"""Start-with-Windows via the per-user Run registry key.

Source: https://learn.microsoft.com/en-us/windows/win32/setupapi/run-and-runonce-registry-keys
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run, value = command line <= 260 chars).
The installer writes the same value name, so the setting and the installer agree.
"""

from __future__ import annotations

import logging
import winreg

from wisp import paths

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Wisp"


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _type = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False


def set_enabled(enabled: bool, command: str | None = None) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            line = command or paths.launch_command()
            if len(line) > 260:
                raise ValueError("Start-up command is longer than the 260 characters allowed.")
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, line)
            log.info("Start with Windows enabled")
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
                log.info("Start with Windows disabled")
            except FileNotFoundError:
                log.info("Start with Windows already disabled")
