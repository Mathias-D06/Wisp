"""Gemini client helpers built on the official google-genai SDK.

Verified against the installed SDK (google-genai 2.29.0): ``genai.Client(api_key=...)``,
``client.models.get(model=...)``, ``client.models.generate_content(model=, contents=, config=)``,
``errors.APIError`` (``.code``, ``.status``, ``.message``) with ``ClientError``/``ServerError``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

NO_KEY_MESSAGE = "Add your Gemini API key in Settings → General to use voice and AI features."
ERROR_TEXT_LIMIT = 300


@dataclass
class KeyCheck:
    ok: bool
    message: str


def make_client(api_key: str):
    from google import genai

    return genai.Client(api_key=api_key)


def describe_error(exc: BaseException, model: str | None = None) -> str:
    """Turn SDK/network errors into a short message for the user (never includes the key)."""
    from google.genai import errors

    if isinstance(exc, errors.APIError):
        details = exc.details if isinstance(exc.details, str) else ""  # WebSocket close reason
        text = f"{exc.status or ''} {exc.message or ''} {details}".lower()
        if "api_key_invalid" in text or "api key not valid" in text:
            return "Google rejected this API key. Check it at https://aistudio.google.com/api-keys."
        if "billing" in text or "location is not supported" in text:
            return (
                "Google requires a billing-enabled key in your region (UK, EEA and Switzerland). "
                "Enable billing for the key's project in AI Studio."
            )
        if exc.code == 404:
            return f"Model {model or ''} is not available for this key. Check the model name."
        if exc.code == 429:
            return "Rate limit or quota reached for this key. Try again shortly."
        if exc.code == 403:
            return "This key is not allowed to use the Gemini API (permission denied)."
        if isinstance(exc, errors.ServerError):
            return "Google's servers returned an error. Try again in a moment."
        return f"Gemini error {exc.code}: {exc.message or exc.status}"
    import httpx  # generate_content's transport (google-genai depends on it)

    if isinstance(exc, OSError | TimeoutError | httpx.TransportError):
        return "Couldn't reach Google. Check your internet connection."
    from wisp.logging_setup import redact

    text = redact(" ".join(str(exc).split()))
    if len(text) > ERROR_TEXT_LIMIT:
        text = text[: ERROR_TEXT_LIMIT - 1].rstrip() + "…"
    return f"Unexpected error ({type(exc).__name__}): {text}" if text else \
        f"Unexpected error: {type(exc).__name__}"


def validate_key(api_key: str, live_model: str, text_model: str) -> KeyCheck:
    """Make cheap test calls: model metadata for both configured models.

    ``models.get`` needs a valid key and proves both model names exist for it.
    """
    try:
        client = make_client(api_key)
        client.models.get(model=live_model)
        client.models.get(model=text_model)
    except Exception as exc:
        message = describe_error(exc, live_model)
        log.warning("API key check failed: %s", message)
        return KeyCheck(False, message)
    return KeyCheck(True, "Key works. Voice and AI features are ready.")
