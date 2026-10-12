"""Rotating file logging with secret redaction."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Google API keys start with "AIza" followed by 35 URL-safe characters.
_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{35}")


class RedactingFilter(logging.Filter):
    """Removes API keys from every log record before it is written."""

    def __init__(self, secret_provider: Callable[[], str | None] | None = None):
        super().__init__()
        self._secret_provider = secret_provider

    def redact(self, text: str) -> str:
        text = _GOOGLE_KEY.sub("[REDACTED]", text)
        secret = self._secret_provider() if self._secret_provider else None
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        if record.exc_info and record.exc_info[1] is not None:
            exc_text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = self.redact(exc_text)
            record.exc_info = None
        return True


def configure(log_folder: Path, secret_provider: Callable[[], str | None]) -> RedactingFilter:
    log_folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_folder / "wisp.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s")
    )
    redactor = RedactingFilter(secret_provider)
    handler.addFilter(redactor)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.addFilter(redactor)
    root.addHandler(console)
    # Network libraries can log request details at DEBUG; keep them quiet.
    for noisy in ("websockets", "httpx", "httpcore", "google_genai", "apscheduler", "comtypes"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return redactor
