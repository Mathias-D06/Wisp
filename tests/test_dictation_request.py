"""The dictation request sent to Gemini: inline WAV, system prompt, low thinking, retry."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import errors, types

from wisp.ai import dictation, gemini


class FakeModels:
    def __init__(self, fail_thinking=False, text='"Meet at 10."'):
        self.requests = []
        self.fail_thinking = fail_thinking
        self.text = text

    def generate_content(self, *, model, contents, config):
        self.requests.append((model, contents, config))
        if self.fail_thinking and config.thinking_config is not None:
            raise errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                                     "message": "thinking_level is not supported"}})
        return SimpleNamespace(text=self.text)


@pytest.fixture
def models(monkeypatch):
    holder = {}

    def make_client(key):
        holder["key"] = key
        return SimpleNamespace(models=holder["models"])

    monkeypatch.setattr(gemini, "make_client", make_client)
    return holder


def test_request_shape(models):
    models["models"] = FakeModels()
    text = dictation.transcribe("AIza-test", "gemini-3.8-flash", b"\x00\x00" * 8000, "English")
    assert text == "Meet at 10."
    model, contents, config = models["models"].requests[0]
    assert model == "gemini-3.8-flash"
    audio = contents[0]
    assert isinstance(audio, types.Part)
    assert audio.inline_data.mime_type == "audio/wav"
    assert audio.inline_data.data[:4] == b"RIFF"
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert "dictation engine" in config.system_instruction


def test_retry_without_thinking(models):
    models["models"] = FakeModels(fail_thinking=True)
    assert dictation.transcribe("k", "older-model", b"\x00\x00" * 8000, "") == "Meet at 10."
    assert len(models["models"].requests) == 2
    assert models["models"].requests[1][2].thinking_config is None
