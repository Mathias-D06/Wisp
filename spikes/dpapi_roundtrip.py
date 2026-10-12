"""Spike: prove pywin32 DPAPI round trip and the CryptUnprotectData return shape.

Run: .venv\\Scripts\\python spikes\\dpapi_roundtrip.py
Expected: CryptUnprotectData returns a (description, data) tuple.
"""

import win32crypt

CRYPTPROTECT_UI_FORBIDDEN = 0x1

blob = win32crypt.CryptProtectData(
    b"secret-value", "Wisp spike", b"entropy", None, None, CRYPTPROTECT_UI_FORBIDDEN
)
print("protected type:", type(blob).__name__, "len:", len(blob))
result = win32crypt.CryptUnprotectData(blob, b"entropy", None, None, CRYPTPROTECT_UI_FORBIDDEN)
print("unprotect result type:", type(result).__name__, "->", result)
try:
    win32crypt.CryptUnprotectData(blob, b"wrong", None, None, CRYPTPROTECT_UI_FORBIDDEN)
except Exception as exc:  # pywintypes.error expected
    print("wrong entropy raises:", type(exc).__name__, exc.args[:2])
