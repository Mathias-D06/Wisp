"""Retrying Gemini when it is busy (D-057), for Screen Assist, Watch mode, reading aloud and
dictation (every ``generate_content`` call).

* **The SDK retries.** ``types.HttpRetryOptions`` on the client's ``HttpOptions`` (google-genai
  2.29.0; Google's "Retry strategy" page documents the same options) with
  ``http_status_codes`` 429 and 503 only: "too many requests" and "high demand". 500 and other
  server errors are not retried; they are reported as they are. The SDK also retries a
  connection that fails or times out. The wait between attempts is tenacity's
  ``wait_exponential_jitter``: initial × base^n plus up to ``jitter`` seconds, capped at
  ``max_delay``. Three attempts wait about 3–5 s, then 6–8 s, so a busy model costs about 20 s
  before Wisp gives up (each 503 itself can take seconds to arrive).
* **Knowing it happens.** httpx's response event hook (``client_args={"event_hooks": …}``,
  passed to ``httpx.Client`` by the SDK) sees each busy answer before the SDK waits. It is
  logged, and ``on_busy`` tells the card "Google is busy, retrying…" when another attempt follows.
* **A timeout per attempt** (``HttpOptions.timeout``, milliseconds), so a request that never
  answers ends in an error instead of waiting forever.
* **One TLS context** for all clients (``client_args["verify"]``; the SDK's websocket context
  comes from ``async_client_args["ssl"]``), instead of two new ones per client.
"""

from __future__ import annotations

import functools
import logging
import os
import ssl
from collections.abc import Callable

log = logging.getLogger(__name__)

RETRY_CODES = (429, 503)
ATTEMPTS = 3  # including the first request
INITIAL_DELAY_S = 3.0
MAX_DELAY_S = 10.0
EXP_BASE = 2.0
JITTER_S = 2.0
TIMEOUT_MS = 40_000  # one attempt; a "high demand" 503 has taken 28 s to arrive
BUSY_TEXT = "Google is busy, retrying…"


def busy_text(attempt: int, attempts: int = ATTEMPTS) -> str:
    """What the card says while waiting for attempt ``attempt + 1``."""
    return f"{BUSY_TEXT} ({attempt + 1} of {attempts})"


def http_options(on_busy: Callable[[str], None] | None = None, attempts: int = ATTEMPTS,
                 timeout_ms: int = TIMEOUT_MS):
    """``types.HttpOptions`` for a client whose ``generate_content`` calls retry 429/503.

    ``on_busy(text)`` runs on the calling (worker) thread when a busy answer arrives and another
    attempt will follow."""
    from google.genai import types

    responses = 0

    def on_response(response) -> None:
        nonlocal responses
        responses += 1
        if response.status_code not in RETRY_CODES:
            return
        again = responses < attempts
        log.warning("Gemini answered %d (%s) on attempt %d of %d%s", response.status_code,
                    "busy" if response.status_code == 503 else "rate limit", responses, attempts,
                    "; retrying" if again else "; giving up")
        if again and on_busy is not None:
            on_busy(busy_text(responses, attempts))

    context = ssl_context()
    return types.HttpOptions(
        timeout=timeout_ms,
        retry_options=types.HttpRetryOptions(
            attempts=attempts, initial_delay=INITIAL_DELAY_S, max_delay=MAX_DELAY_S,
            exp_base=EXP_BASE, jitter=JITTER_S, http_status_codes=list(RETRY_CODES)),
        client_args={"verify": context, "event_hooks": {"response": [on_response]}},
        async_client_args={"ssl": context},  # the SDK's websocket context; httpx drops it
    )


@functools.cache
def ssl_context() -> ssl.SSLContext:
    """One TLS context for every client, made the way the SDK makes its own (certifi's CA
    bundle, or SSL_CERT_FILE / SSL_CERT_DIR). Without it each ``genai.Client`` loads the
    bundle twice, about 0.45 s on this PC, for every request."""
    import certifi

    return ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE", certifi.where()),
                                      capath=os.environ.get("SSL_CERT_DIR"))


def warm_up() -> None:
    """Import the SDK and load the CA bundle ahead of the first request (about a second)."""
    try:
        from google.genai import types  # noqa: F401

        ssl_context()
    except Exception as exc:  # the first request reports any real problem
        log.info("Gemini warm-up skipped: %s", exc)


def is_busy(exc: BaseException) -> bool:
    """Gemini's "high demand" answer (after the retries)."""
    from google.genai import errors

    return isinstance(exc, errors.APIError) and exc.code == 503
