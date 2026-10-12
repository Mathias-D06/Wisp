"""Integration tests: LiveSessionManager against a fake Live server with scripted replies."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors

from tests.fakes import (
    DirectUi,
    FakeLiveServer,
    audio_msg,
    go_away,
    interrupted,
    resumption,
    tool_call,
    transcript_msg,
    turn_complete,
    until,
)
from wisp.live.session import LiveCallbacks, LiveSessionManager, LiveState, parse_duration
from wisp.settings import Settings
from wisp.stores.action_log import ActionLog
from wisp.tools.base import Risk, Tool, obj, string
from wisp.tools.confirm import ConfirmationManager
from wisp.tools.dispatcher import Dispatcher
from wisp.tools.registry import ToolRegistry
from wisp.tools.safety import SafetyPolicy, TaintTracker


class Recorder:
    def __init__(self):
        self.states: list[tuple[LiveState, str]] = []
        self.audio: list[bytes] = []
        self.interrupts = 0
        self.user_final: list[str] = []
        self.model_final: list[str] = []
        self.tools: list[tuple[str, str]] = []
        self.playing = False

    def callbacks(self) -> LiveCallbacks:
        def model_text(text, final):
            if final:
                self.model_final.append(text)

        def on_interrupt():
            self.interrupts += 1

        return LiveCallbacks(
            state=lambda s, d: self.states.append((s, d)),
            model_audio=self.audio.append,
            interrupted=on_interrupt,
            user_final=self.user_final.append,
            model_text=model_text,
            tool_activity=lambda n, s: self.tools.append((n, s)),
        )


class Env:
    def __init__(self, db, loop, always_listening=False, idle=3600.0, has_key=True):
        self.server = FakeLiveServer()
        self.rec = Recorder()
        self.settings = Settings()
        self.settings.audio.always_listening = always_listening
        self.opened: list[str] = []
        registry = ToolRegistry()
        registry.register(Tool("open_app", "d", obj({"name": string("n")}, ["name"]),
                               self._open_app, "apps"))
        registry.register(Tool("power_off", "d", obj(), lambda c, a: "off", "power",
                               risk=Risk.CONFIRM))
        self.confirmations = ConfirmationManager()
        self.dispatcher = Dispatcher(
            registry, SafetyPolicy(lambda: self.settings, TaintTracker(lambda: 5)),
            self.confirmations, ActionLog(db), None, SimpleNamespace(ui=DirectUi()),
        )
        self.dispatcher.bind_loop(loop)
        self.key = has_key
        callbacks = self.rec.callbacks()
        callbacks.user_final = self._user_final
        self.manager = LiveSessionManager(
            loop, self.server, lambda handle: SimpleNamespace(
                session_resumption=SimpleNamespace(handle=handle)),
            self.dispatcher, callbacks,
            has_key=lambda: self.key, idle_timeout_s=lambda: idle,
            always_listening=lambda: self.settings.audio.always_listening,
            is_playing=lambda: self.rec.playing,
            tick_s=0.02, backoff_base=0.05, backoff_max=0.2,
        )

    def _user_final(self, text):
        self.rec.user_final.append(text)
        self.confirmations.on_user_utterance(text)

    def _open_app(self, ctx, args):
        self.opened.append(args["name"])
        return f"opened {args['name']}"

    def close(self):
        self.manager.disconnect()
        self.dispatcher.shutdown()


@pytest.fixture
async def env(db):
    e = Env(db, asyncio.get_running_loop())
    yield e
    e.close()
    await asyncio.sleep(0.05)


def reply_after_turn(*messages):
    """Rule: when the client ends an activity, the server answers with ``messages``."""
    def rule(session, kind, value):
        return list(messages) if kind == "activity_end" else None
    return rule


async def test_push_to_talk_turn(env):
    env.server.rules.append(reply_after_turn(
        transcript_msg(user="hello", finished=True), audio_msg(), transcript_msg(model="Hi!"),
        turn_complete()))
    env.manager.begin_turn()
    env.manager.push_audio(b"\x00\x00" * 512)
    env.manager.end_turn()
    await until(lambda: env.rec.model_final)
    session = env.server.current
    assert session.kinds()[:3] == ["activity_start", "audio", "activity_end"]
    assert session.sent[1][1].mime_type == "audio/pcm;rate=16000"
    assert env.rec.audio and env.rec.user_final == ["hello"] and env.rec.model_final == ["Hi!"]
    assert env.manager.state == LiveState.READY


async def test_tool_call_mid_conversation(env):
    def rule(session, kind, value):
        if kind == "activity_end":
            return [transcript_msg(user="open spotify", finished=True),
                    tool_call(("c1", "open_app", {"name": "Spotify"}))]
        if kind == "tool_response":
            return [audio_msg(), transcript_msg(model="Opening Spotify."), turn_complete()]
        return None

    env.server.rules.append(rule)
    env.manager.begin_turn()
    env.manager.end_turn()
    await until(lambda: env.rec.model_final == ["Opening Spotify."])
    assert env.opened == ["Spotify"]
    responses = next(v for k, v in env.server.current.sent if k == "tool_response")
    assert responses[0].id == "c1" and responses[0].response["result"] == "opened Spotify"
    assert env.rec.tools == [("open_app", "start"), ("open_app", "end")]


async def test_barge_in_clears_playback_locally_and_on_server_interrupt(env):
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.server.current.push(audio_msg())
    await until(lambda: env.rec.audio)
    before = env.rec.interrupts
    env.manager.begin_turn()  # user starts talking over the model
    await until(lambda: env.rec.interrupts == before + 1)
    env.server.current.push(audio_msg())  # stale audio from the old answer
    await asyncio.sleep(0.05)
    assert len(env.rec.audio) == 1  # suppressed while the user holds the key
    env.server.current.push(interrupted())
    await until(lambda: env.rec.interrupts == before + 2)


async def test_go_away_reconnects_with_latest_handle(env):
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    first = env.server.current
    first.push(resumption("h-1"), resumption("h-ignored", resumable=False), go_away(0.2))
    await until(lambda: len(env.server.sessions) == 2)
    assert first.closed
    assert env.server.current.handle == "h-1"
    await until(lambda: env.manager.state == LiveState.READY)
    assert not any(s == LiveState.OFFLINE for s, _ in env.rec.states)


async def test_network_error_shows_status_and_recovers(env):
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.server.current.push(resumption("h-7"))
    env.server.connect_errors = [OSError("network down"), OSError("network down")]
    env.server.current.push(ConnectionResetError("cable unplugged"))
    await until(lambda: any(s == LiveState.OFFLINE for s, _ in env.rec.states))
    offline_detail = next(d for s, d in env.rec.states if s == LiveState.OFFLINE)
    assert "internet" in offline_detail and "Retrying" in offline_detail
    await until(lambda: env.manager.state == LiveState.READY, timeout=5)
    assert env.server.current.handle == "h-7"


async def test_idle_timeout_closes_and_next_turn_resumes(db):
    loop = asyncio.get_running_loop()
    e = Env(db, loop, idle=0.1)
    try:
        e.manager.connect()
        await until(lambda: e.manager.state == LiveState.READY)
        e.server.current.push(resumption("h-idle"))
        await until(lambda: e.manager.state == LiveState.IDLE)
        assert e.server.current.closed
        e.manager.begin_turn()
        await until(lambda: len(e.server.sessions) == 2)
        assert e.server.current.handle == "h-idle"
    finally:
        e.close()


async def test_idle_not_triggered_while_speaking(db):
    e = Env(db, asyncio.get_running_loop(), idle=0.05)
    try:
        e.rec.playing = True
        e.manager.connect()
        await until(lambda: e.manager.state == LiveState.READY)
        await asyncio.sleep(0.2)
        assert e.manager.state == LiveState.READY
    finally:
        e.close()


async def test_fatal_key_error_stops_retrying(env):
    env.server.connect_errors = [errors.ClientError(403, {"error": {
        "code": 403, "message": "Permission denied", "status": "PERMISSION_DENIED"}})]
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.ERROR)
    await asyncio.sleep(0.1)
    assert len(env.server.configs) == 1


async def test_failed_resume_starts_fresh(env):
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.server.current.push(resumption("stale"))
    env.server.connect_errors = [errors.ClientError(400, {"error": {
        "code": 400, "message": "Invalid handle", "status": "INVALID_ARGUMENT"}})]
    env.server.current.push(ConnectionResetError())
    await until(lambda: len(env.server.sessions) == 2, timeout=5)
    assert env.server.configs[1].session_resumption.handle == "stale"
    assert env.server.current.handle is None


async def test_no_key_reports_add_key(db):
    e = Env(db, asyncio.get_running_loop(), has_key=False)
    try:
        e.manager.begin_turn()
        await until(lambda: e.manager.state == LiveState.NO_KEY)
        assert "API key" in e.manager.state_detail
        assert e.server.configs == []
    finally:
        e.close()


async def test_typed_text_uses_realtime_text(env):
    env.manager.send_text("what time is it")
    await until(lambda: env.server.sessions and env.server.current.sent)
    assert env.server.current.sent[0] == ("text", "what time is it")


async def test_always_listening_streams_without_activity_markers(db):
    e = Env(db, asyncio.get_running_loop(), always_listening=True)
    try:
        e.manager.connect()
        await until(lambda: e.manager.state == LiveState.READY)
        e.manager.push_audio(b"\x00\x00" * 512)
        e.manager.audio_stream_end()
        await until(lambda: len(e.server.current.sent) == 2)
        assert e.server.current.kinds() == ["audio", "audio_stream_end"]
    finally:
        e.close()


async def test_spoken_yes_confirms_through_transcription(env):
    def rule(session, kind, value):
        if kind == "activity_end" and not any(k == "tool_response" for k, _ in session.sent):
            return [transcript_msg(user="turn off the pc", finished=True),
                    tool_call(("p1", "power_off", {}))]
        if kind == "activity_end":
            return [transcript_msg(user="yes", finished=True)]
        return None

    env.server.rules.append(rule)
    env.manager.begin_turn()
    env.manager.end_turn()
    await until(lambda: env.server.sessions
                and any(k == "tool_response" for k, _ in env.server.current.sent))
    first = next(v for k, v in env.server.current.sent if k == "tool_response")[0].response
    assert first["status"] == "needs_confirmation"
    env.manager.begin_turn()
    env.manager.end_turn()
    await until(lambda: env.confirmations.get(first["confirmation_id"]).state != "pending")
    env.server.current.push(tool_call(("p2", "confirm_action",
                                       {"confirmation_id": first["confirmation_id"]})))
    await until(lambda: len([1 for k, _ in env.server.current.sent if k == "tool_response"]) == 2)
    second = [v for k, v in env.server.current.sent if k == "tool_response"][1][0].response
    assert second["ok"] is True and second["result"] == "off"


async def test_long_conversation_survives_many_reconnects(env):
    """Simulates a 30-minute conversation: three ~10-minute connections ended by GoAway,
    tool calls on each, and a network blip. The server verifies every reconnect carries
    the latest handle, so no context is lost."""
    counter = {"n": 0}

    def rule(session, kind, value):
        if kind == "activity_end":
            counter["n"] += 1
            n = counter["n"]
            return [tool_call((f"t{n}", "open_app", {"name": f"App{n}"}))]
        if kind == "tool_response":
            n = counter["n"]
            return [resumption(f"h{n}"), audio_msg(), turn_complete()]
        return None

    env.server.rules.append(rule)
    for round_number in range(1, 7):
        env.manager.begin_turn()
        env.manager.push_audio(b"\x00\x00" * 512)
        env.manager.end_turn()
        await until(lambda n=round_number: env.manager.handle == f"h{n}")
        if round_number in (2, 4):
            env.server.current.push(go_away(0.1))
            await until(lambda n=round_number: env.server.current.handle == f"h{n}")
            await until(lambda: env.manager.state == LiveState.READY)
        if round_number == 5:
            env.server.current.push(ConnectionResetError("blip"))
            await until(lambda n=round_number: env.server.current.handle == f"h{n}"
                        and env.manager.state == LiveState.READY, timeout=5)
    assert env.opened == [f"App{i}" for i in range(1, 7)]
    assert len(env.server.sessions) == 4
    assert [s.handle for s in env.server.sessions] == [None, "h2", "h4", "h5"]


def test_parse_duration():
    assert parse_duration("12.5s") == 12.5
    assert parse_duration("3s") == 3.0
    assert parse_duration(None) == 0.0
    assert parse_duration("junk") == 0.0
