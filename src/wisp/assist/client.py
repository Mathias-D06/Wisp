"""Gemini for Screen Assist (D-052), behind a small interface so tests use a fake.

* ``answer``: one stateless ``generate_content`` call (as dictation, D-023: nothing is stored as
  an Interaction). The conversation so far is sent each time as ``contents``; screenshots are
  inline JPEG parts (``types.Part.from_bytes``), with ``media_resolution`` LOW for Watch mode.
  Watch mode asks for JSON (``response_mime_type`` + ``response_json_schema``).
* ``speak``: the same text read aloud by a Gemini TTS model (``response_modalities=["AUDIO"]``,
  ``speech_config`` with the voice chosen in Settings → Loadout), 24 kHz mono PCM for the
  player. The data may come as raw PCM or a WAV file; both are handled.
* Token counts come back from ``usage_metadata`` for the Stats estimate.
* Each call holds its ``genai.Client`` in a ``with`` block for the whole request. A temporary
  client (``make_client(key).models.generate_content(...)``) is garbage-collected as soon as
  ``.models`` has been read, and ``Client.__del__`` closes its HTTP client before the request is
  sent: "Cannot send a request, as the client has been closed" (D-054).
"""

from __future__ import annotations

import io
import logging
import re
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class Part:
    """One piece of a turn: text, a JPEG screenshot or a WAV question."""

    text: str = ""
    jpeg: bytes = b""
    wav: bytes = b""


@dataclass
class Turn:
    role: str  # "user" | "model"
    parts: list[Part] = field(default_factory=list)


@dataclass
class Reply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Speech:
    pcm: bytes  # 16-bit mono
    rate: int = 24000
    input_tokens: int = 0
    output_tokens: int = 0


class AssistModel(Protocol):
    def model_name(self) -> str: ...

    def answer(self, turns: list[Turn], system: str, json_schema: dict | None = None,
               low_resolution: bool = False) -> Reply: ...

    def speak(self, text: str, voice: str) -> Speech: ...


def _contents(turns: list[Turn]):
    from google.genai import types

    contents = []
    for turn in turns:
        parts = []
        for part in turn.parts:
            if part.text:
                parts.append(types.Part.from_text(text=part.text))
            if part.jpeg:
                parts.append(types.Part.from_bytes(data=part.jpeg, mime_type="image/jpeg"))
            if part.wav:
                parts.append(types.Part.from_bytes(data=part.wav, mime_type="audio/wav"))
        contents.append(types.Content(role=turn.role, parts=parts))
    return contents


def pcm_from(data: bytes, mime_type: str) -> tuple[bytes, int]:
    """(16-bit mono PCM, sample rate) from TTS output: a WAV file or raw L16 PCM."""
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data), "rb") as wav:
            return wav.readframes(wav.getnframes()), wav.getframerate()
    match = re.search(r"rate=(\d+)", mime_type or "")
    return data, int(match.group(1)) if match else 24000


class GeminiAssistModel:
    def __init__(self, api_key: Callable[[], str], model: Callable[[], str],
                 tts_model: Callable[[], str],
                 make_client: Callable[[str], object] | None = None) -> None:
        """``make_client``: key → ``genai.Client`` (the self-check points one at a loopback
        stand-in for the API)."""
        self._api_key = api_key
        self._model = model
        self._tts_model = tts_model
        self._make_client = make_client

    def model_name(self) -> str:
        return self._model()

    def _client(self):
        from wisp.ai.gemini import make_client

        return (self._make_client or make_client)(self._api_key())

    def answer(self, turns: list[Turn], system: str, json_schema: dict | None = None,
               low_resolution: bool = False) -> Reply:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            media_resolution=(types.MediaResolution.MEDIA_RESOLUTION_LOW if low_resolution
                              else types.MediaResolution.MEDIA_RESOLUTION_MEDIUM),
        )
        if json_schema is not None:
            config.response_mime_type = "application/json"
            config.response_json_schema = json_schema
        with self._client() as client:
            response = client.models.generate_content(
                model=self._model(), contents=_contents(turns), config=config)
        usage = response.usage_metadata
        return Reply(response.text or "",
                     int(getattr(usage, "prompt_token_count", 0) or 0),
                     int(getattr(usage, "candidates_token_count", 0) or 0)
                     + int(getattr(usage, "thoughts_token_count", 0) or 0))

    def speak(self, text: str, voice: str) -> Speech:
        from google.genai import types

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))))
        with self._client() as client:
            response = client.models.generate_content(
                model=self._tts_model(), contents=text, config=config)
        usage = response.usage_metadata
        tokens = (int(getattr(usage, "prompt_token_count", 0) or 0),
                  int(getattr(usage, "candidates_token_count", 0) or 0))
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                pcm, rate = pcm_from(part.inline_data.data, part.inline_data.mime_type or "")
                return Speech(pcm, rate, *tokens)
        return Speech(b"", 24000, *tokens)
