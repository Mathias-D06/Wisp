from __future__ import annotations

import logging

import pytest

from wisp.keystore import KeyStore, looks_like_key, mask
from wisp.logging_setup import RedactingFilter

FAKE_KEY = "AIza" + "B" * 35


def test_mask_never_reveals_middle():
    assert mask(FAKE_KEY) == "AIza…BBBB"
    assert FAKE_KEY not in mask(FAKE_KEY)
    assert mask(None) == "(not set)"
    assert mask("short") == "………"


def test_key_shape():
    assert looks_like_key(FAKE_KEY)
    assert not looks_like_key("not a key")
    assert not looks_like_key("")


@pytest.mark.windows
def test_dpapi_round_trip(tmp_path):
    path = tmp_path / "secrets.bin"
    store = KeyStore(path)
    assert store.get() is None
    store.set(FAKE_KEY)
    assert FAKE_KEY.encode() not in path.read_bytes()  # encrypted at rest
    assert KeyStore(path).get() == FAKE_KEY
    store.clear()
    assert KeyStore(path).get() is None


@pytest.mark.windows
def test_tampered_file_returns_none(tmp_path):
    path = tmp_path / "secrets.bin"
    path.write_bytes(b"garbage")
    assert KeyStore(path).get() is None


def test_redacting_filter_removes_keys():
    custom = "my-custom-secret-123456"
    redactor = RedactingFilter(lambda: custom)
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "key=%s other=%s", (FAKE_KEY, custom), None
    )
    redactor.filter(record)
    text = record.getMessage()
    assert FAKE_KEY not in text and custom not in text
    assert text.count("[REDACTED]") == 2


def test_redacting_filter_cleans_tracebacks():
    redactor = RedactingFilter(lambda: None)
    try:
        raise RuntimeError(f"bad key {FAKE_KEY}")
    except RuntimeError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "oops", (), sys.exc_info())
    redactor.filter(record)
    assert FAKE_KEY not in (record.exc_text or "")
