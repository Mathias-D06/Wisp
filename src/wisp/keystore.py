"""Gemini API key storage protected with Windows DPAPI (current-user scope).

The key is encrypted with ``CryptProtectData`` so only the same Windows user on the same PC can
decrypt it. It is never logged; use :func:`mask` whenever it must be shown.
Source: https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

log = logging.getLogger(__name__)

CRYPTPROTECT_UI_FORBIDDEN = 0x1
_ENTROPY = b"Wisp/api-key/v1"
_KEY_SHAPE = re.compile(r"^[A-Za-z0-9_\-\.]{20,200}$")


def mask(key: str | None) -> str:
    """Show only enough of a key to recognise it, e.g. ``AIza…9xQk``."""
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return "…" * 3
    return f"{key[:4]}…{key[-4:]}"


def looks_like_key(key: str) -> bool:
    return bool(_KEY_SHAPE.match(key.strip()))


class KeyStore:
    """Stores one secret (the Gemini API key) in an encrypted file."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._cached: str | None = None
        self._loaded = False
        self._listeners: list = []

    def subscribe(self, listener) -> None:
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener(self.has_key())
            except Exception:
                log.exception("Key listener failed")

    def get(self) -> str | None:
        with self._lock:
            if not self._loaded:
                self._cached = self._read()
                self._loaded = True
            return self._cached

    def has_key(self) -> bool:
        return bool(self.get())

    def set(self, key: str) -> None:
        key = key.strip()
        if not looks_like_key(key):
            raise ValueError("That does not look like an API key.")
        import win32crypt

        blob = win32crypt.CryptProtectData(
            key.encode("utf-8"), "Wisp API key", _ENTROPY, None, None, CRYPTPROTECT_UI_FORBIDDEN
        )
        with self._lock:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_bytes(blob)
            tmp.replace(self._path)
            self._cached = key
            self._loaded = True
        log.info("API key saved (%s)", mask(key))
        self._notify()

    def clear(self) -> None:
        with self._lock:
            if self._path.exists():
                self._path.unlink()
            self._cached = None
            self._loaded = True
        log.info("API key removed")
        self._notify()

    def _read(self) -> str | None:
        if not self._path.exists():
            return None
        try:
            import win32crypt

            _description, data = win32crypt.CryptUnprotectData(
                self._path.read_bytes(), _ENTROPY, None, None, CRYPTPROTECT_UI_FORBIDDEN
            )
            return data.decode("utf-8")
        except Exception as exc:
            # Happens if the file was copied from another user/PC; the user must re-enter it.
            log.error("Stored API key could not be decrypted: %s", type(exc).__name__)
            return None
