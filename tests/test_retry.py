"""D-057: Gemini's busy answers (503 "high demand", 429) are retried by the SDK with backoff and
jitter; the card hears about it; a fallback text model answers only after the retries fail on
503, and says so; 500 is reported, not retried. The real google-genai client talks to the
loopback stand-in (wisp.ai.loopback), or a fake client stands in; nothing calls Google."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from google.genai import errors

from wisp.ai import dictation, retry
from wisp.ai.gemini import describe_error
from wisp.ai.loopback import GeminiLoopback
from wisp.assist.client import GeminiAssistModel, Part, Turn

TURNS = [Turn("user", [Part(text="What's on screen?")])]


@pytest.fixture(autouse=True)
def quick_retries(monkeypatch):
    """The real policy waits 3–5 s, then 6–8 s; tests wait a few milliseconds."""
    monkeypatch.setattr(retry, "INITIAL_DELAY_S", 0.01)
    monkeypatch.setattr(retry, "JITTER_S", 0.01)


def model_on(stub, fallback=""):
    return GeminiAssistModel(lambda: "test-key", lambda: "gemini-3.8-flash",
                             lambda: "gemini-3.8-flash-tts", make_client=stub.client,
                             fallback_model=lambda: fallback)


def test_the_policy_is_three_attempts_about_twenty_seconds_on_429_and_503():
    options = retry.http_options()
    policy = options.retry_options
    assert policy.attempts == 3 and policy.http_status_codes == [429, 503]
    assert options.timeout == 40_000
    assert (retry.INITIAL_DELAY_S, retry.MAX_DELAY_S, retry.EXP_BASE) == (0.01, 10.0, 2.0)


def test_real_policy_waits_add_up_to_about_twenty_seconds(monkeypatch):
    monkeypatch.undo()  # the real constants
    import tenacity

    wait = tenacity.wait_exponential_jitter(initial=retry.INITIAL_DELAY_S, max=retry.MAX_DELAY_S,
                                            exp_base=retry.EXP_BASE, jitter=retry.JITTER_S)
    waits = [wait(SimpleNamespace(attempt_number=n)) for n in range(1, retry.ATTEMPTS)]
    assert 3.0 <= waits[0] <= 5.0 and 6.0 <= waits[1] <= 8.0 and sum(waits) <= 13.0


def test_two_busy_answers_then_an_answer():
    notes = []
    with GeminiLoopback("Fine now.") as stub:
        stub.busy["gemini-3.8-flash"] = 2
        reply = model_on(stub).answer(TURNS, "system", on_busy=notes.append)
    assert reply.text == "Fine now." and reply.model == "gemini-3.8-flash"
    assert reply.fallback_from == ""
    assert stub.models_asked() == ["gemini-3.8-flash"] * 3
    assert notes == ["Google is busy, retrying… (2 of 3)", "Google is busy, retrying… (3 of 3)"]


def test_still_busy_after_three_attempts_is_explained():
    with GeminiLoopback() as stub:
        stub.busy["gemini-3.8-flash"] = -1
        with pytest.raises(errors.ServerError) as raised:
            model_on(stub).answer(TURNS, "system")
    assert len(stub.requests) == 3
    message = describe_error(raised.value)
    assert "overloaded" in message and "503" in message and "Try again" in message


def test_the_fallback_model_answers_only_after_503_and_says_so():
    notes = []
    with GeminiLoopback("From the fallback.") as stub:
        stub.busy["gemini-3.8-flash"] = -1
        reply = model_on(stub, fallback="gemini-3.6-flash").answer(TURNS, "system",
                                                                    on_busy=notes.append)
    assert stub.models_asked() == ["gemini-3.8-flash"] * 3 + ["gemini-3.6-flash"]
    assert (reply.text, reply.model, reply.fallback_from) == (
        "From the fallback.", "gemini-3.6-flash", "gemini-3.8-flash")
    assert notes[-1] == "Google is busy; asking gemini-3.6-flash instead…"


def test_the_card_names_the_model_that_answered():
    from tests.test_screen_assist import CODE, FakeSystem, Window, capturer, editor
    from wisp.assist.engine import AssistEngine
    from wisp.ui.island.assist_tab import transcript_markdown

    system = FakeSystem(Window(1, "main.py - Code", "Code"), {1: editor(CODE)})
    with GeminiLoopback("A Python file.") as stub:
        stub.busy["gemini-3.8-flash"] = -1
        engine = AssistEngine(model_on(stub, fallback="gemini-3.6-flash"), capturer(system),
                              lambda: "English (UK)")
        exchange = engine.ask()
    assert exchange.notes == ["Answered by gemini-3.6-flash: gemini-3.8-flash was busy."]
    assert "Answered by gemini" in transcript_markdown([exchange])


def test_no_fallback_when_none_is_set_or_it_is_the_same_model():
    for fallback in ("", "gemini-3.8-flash"):
        with GeminiLoopback() as stub:
            stub.busy["gemini-3.8-flash"] = -1
            with pytest.raises(errors.ServerError):
                model_on(stub, fallback=fallback).answer(TURNS, "system")
        assert stub.models_asked() == ["gemini-3.8-flash"] * 3


def test_a_busy_fallback_gives_up_after_two_attempts():
    with GeminiLoopback() as stub:
        stub.busy["gemini-3.8-flash"] = stub.busy["gemini-3.6-flash"] = -1
        with pytest.raises(errors.ServerError):
            model_on(stub, fallback="gemini-3.6-flash").answer(TURNS, "system")
    assert stub.models_asked() == ["gemini-3.8-flash"] * 3 + ["gemini-3.6-flash"] * 2


# ----- with a fake client ---------------------------------------------------------------------
class FakeClient:
    """Raises the scripted errors (one per call), then answers."""

    def __init__(self, script):
        self.script = script
        self.models = SimpleNamespace(generate_content=self.generate_content)
        self.options = []

    def __call__(self, key, http_options=None):
        self.options.append(http_options)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def generate_content(self, model, contents, config):
        if self.script:
            raise self.script.pop(0)
        return SimpleNamespace(text=f"answered by {model}", usage_metadata=None)


def server_error(code: int, status: str, message: str) -> errors.ServerError:
    return errors.ServerError(code, {"error": {"code": code, "status": status,
                                               "message": message}})


def test_500_and_429_are_not_reasons_for_the_fallback():
    for error in (server_error(500, "INTERNAL", "Internal error"),
                  errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                                     "message": "quota"}})):
        fake = FakeClient([error])
        model = GeminiAssistModel(lambda: "k", lambda: "gemini-3.8-flash", lambda: "t",
                                  make_client=fake, fallback_model=lambda: "gemini-3.6-flash")
        with pytest.raises(errors.APIError):
            model.answer(TURNS, "system")
    assert describe_error(server_error(500, "INTERNAL", "x")) == (
        "Google's servers returned an error (500). Try again in a moment.")


def test_every_request_carries_the_retry_options():
    fake = FakeClient([server_error(503, "UNAVAILABLE", "high demand")])
    model = GeminiAssistModel(lambda: "k", lambda: "gemini-3.8-flash", lambda: "t",
                              make_client=fake, fallback_model=lambda: "gemini-3.6-flash")
    assert model.answer(TURNS, "system").text == "answered by gemini-3.6-flash"
    attempts = [options.retry_options.attempts for options in fake.options]
    assert attempts == [3, 2]  # the usual model, then the fallback's shorter policy


def test_500_is_not_retried_by_the_sdk():
    with GeminiLoopback() as stub:
        stub.busy["gemini-3.8-flash"] = 0
        original = stub.answer

        def internal(path):
            if "gemini-3.8-flash:" in path:
                return 500, {"error": {"code": 500, "status": "INTERNAL", "message": "oops"}}
            return original(path)

        stub.answer = internal
        with pytest.raises(errors.ServerError):
            model_on(stub).answer(TURNS, "system")
    assert len(stub.requests) == 1


# ----- reading aloud and dictation retry the same way ----------------------------------------
def test_reading_aloud_is_retried():
    with GeminiLoopback(pcm=b"\x01\x00" * 480) as stub:
        stub.busy["gemini-3.8-flash-tts"] = 1
        speech = model_on(stub).speak("Hello.", "Kore")
    assert speech.pcm == b"\x01\x00" * 480 and len(stub.requests) == 2


def test_dictation_is_retried_and_reports_it():
    notes = []
    with GeminiLoopback("Meet at 10.") as stub:
        stub.busy["gemini-3.8-flash"] = 1
        text = dictation.transcribe("k", "gemini-3.8-flash", b"\x00\x00" * 8000, "English",
                                    on_busy=notes.append, make_client=stub.client)
    assert text == "Meet at 10." and len(stub.requests) == 2
    assert notes == ["Google is busy, retrying… (2 of 3)"]


@pytest.mark.qt
def test_the_dictation_hud_says_google_is_busy(qtbot):
    from tests.test_dictation import Recorder, make

    rec = Recorder()
    controller, mic, hud, _stats = make(rec)
    gate = threading.Event()

    def slow_transcribe(pcm, on_busy):
        on_busy("Google is busy, retrying… (2 of 3)")
        gate.wait(5)
        return "Meet at 10."

    controller.deps.transcribe = slow_transcribe
    controller.start()
    mic.feed(1.5)
    controller.stop()
    qtbot.waitUntil(lambda: "Google is busy, retrying… (2 of 3)" in hud.messages, timeout=3000)
    gate.set()


# ----- the setting ------------------------------------------------------------------------------
def test_the_fallback_setting_is_off_by_default_and_validated():
    from wisp.settings import Settings, validate

    settings = Settings()
    assert settings.ai.fallback_text_model == ""
    settings.ai.fallback_text_model = "gemini 3.6 flash"
    assert any("fallback" in problem for problem in validate(settings))
    settings.ai.fallback_text_model = "gemini-3.6-flash"
    assert not validate(settings)


@pytest.mark.qt
def test_settings_general_offers_the_fallback_models(qtbot, tmp_path, monkeypatch):
    from wisp import startup
    from wisp.keystore import KeyStore
    from wisp.settings import SettingsStore
    from wisp.ui.settings.general_page import GeneralPage

    monkeypatch.setattr(startup, "is_enabled", lambda: False)
    store = SettingsStore(tmp_path / "s.json")
    page = GeneralPage(store, KeyStore(tmp_path / "k.bin"))
    qtbot.addWidget(page)
    page.load(store.get())
    combo = page.fallback_model
    assert combo.currentText() == "Off"
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Off", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
    combo.setCurrentIndex(1)
    settings = store.get()
    page.apply(settings)
    assert settings.ai.fallback_text_model == "gemini-3.6-flash"
    combo.setEditText("gemini-4-argon")  # any model can be typed
    page.apply(settings)
    assert settings.ai.fallback_text_model == "gemini-4-argon"
    page.load(settings)
    assert combo.currentText() == "gemini-4-argon"
    combo.setCurrentIndex(0)
    page.apply(settings)
    assert settings.ai.fallback_text_model == ""
