"""run_command (skill group "terminal"): off by default, behind Settings → Safety → "Allow
terminal commands" (F12.3). When enabled, every command still asks first and can never be
auto-approved (DECISIONS.md D-034).

Runs Windows PowerShell 5.1 (``powershell.exe``, present on every Windows 10/11) as the signed-in
user — never elevated — with ``-NoProfile -NonInteractive``, no console window, stdin closed,
a time limit and a capped, untrusted output. Sources: learn.microsoft.com
powershell/module/microsoft.powershell.core/about/about_powershell_exe (-NoProfile,
-NonInteractive, -Command); taskkill /T /F ends the process tree on timeout.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from wisp.tools.base import Risk, Tool, ToolContext, ToolError, integer, obj, string

CREATE_NO_WINDOW = 0x08000000
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300
MAX_OUTPUT = 4000
UTF8_PREAMBLE = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "


def powershell_args(command: str) -> list[str]:
    # The user's execution policy is left as it is (no -ExecutionPolicy override).
    return ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
            UTF8_PREAMBLE + command]


def clip(text: str, limit: int = MAX_OUTPUT) -> str:
    text = text.replace("\r\n", "\n").strip()
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n… [{len(text) - limit} characters cut] …\n{text[-half:]}"


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                   creationflags=CREATE_NO_WINDOW, check=False)


def run_command(ctx: ToolContext, args: dict) -> dict:
    command = (args.get("command") or "").strip()
    if not command:
        raise ToolError("No command given.")
    timeout = max(1, min(int(args.get("timeout_s") or DEFAULT_TIMEOUT), MAX_TIMEOUT))
    folder = Path(os.path.expandvars(args.get("folder") or str(Path.home()))).expanduser()
    if not folder.is_dir():
        raise ToolError(f"Folder not found: {folder}")
    process = subprocess.Popen(
        powershell_args(command), cwd=str(folder), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW,
        encoding="utf-8", errors="replace")
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process.pid)
        stdout, stderr = process.communicate()
        return {"exit_code": None, "timed_out": True,
                "output": clip(stdout or ""), "errors": clip(stderr or "", 1000),
                "note": f"Stopped after {timeout} s."}
    result = {"exit_code": process.returncode, "output": clip(stdout or "")}
    if stderr and stderr.strip():
        result["errors"] = clip(stderr, 1500)
    return result


def tools() -> list[Tool]:
    return [
        Tool("run_command", "Run a PowerShell command as the user (asks first every time). "
             "Prefer other tools when one fits.",
             obj({"command": string("The PowerShell command"),
                  "folder": string("Working folder (default: the user's home folder)"),
                  "timeout_s": integer("Time limit in seconds (default 60, max 300)")},
                 ["command"]),
             run_command, "terminal", risk=Risk.DISABLED, enabled_by="allow_terminal",
             tier_when_enabled=Risk.CONFIRM, untrusted_output=True,
             timeout_s=MAX_TIMEOUT + 15,
             summary=lambda a: f"run in PowerShell: {a.get('command', '')[:160]}"),
    ]
