"""Integration tests: LiveSessionManager against a fake Live server with scripted replies."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors

from tests.fakes import (
    QUIET_CHUNK,
    SILENT_CHUNK,
    SPEECH_CHUNK,
    DirectUi,
    FakeLiveServer,
    audio_msg,
    go_away,
    interrupted,
    resumption,
    speak,
    tool_call,
    transcript_msg,
    turn_complete,
    until,
)
from wisp.live import session as session_module
from wisp.live.session import (
    LiveCallbacks,
    LiveSessionManager,
    LiveState,
    classify_error,
    parse_duration,
)
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
        self.dropped: list[str] = []
        self.user_rows: list[tuple[int, str, bool]] = []
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
            turn_dropped=self.dropped.append,
            user_text=lambda turn, text, final: self.user_rows.append((turn, text, final)),
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
    speak(env.manager)
    env.manager.end_turn()
    await until(lambda: env.rec.model_final)
    session = env.server.current
    assert session.kinds()[:12] == ["activity_start"] + ["audio"] * 10 + ["activity_end"]
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
    speak(env.manager)
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
    speak(env.manager)
    env.manager.end_turn()
    await until(lambda: env.server.sessions
                and any(k == "tool_response" for k, _ in env.server.current.sent))
    first = next(v for k, v in env.server.current.sent if k == "tool_response")[0].response
    assert first["status"] == "needs_confirmation"
    env.manager.begin_turn()
    speak(env.manager)
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
        speak(env.manager)
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


# ----- short push-to-talk turns (D-038) ------------------------------------------------------
async def test_tap_sends_nothing_and_hints(env):
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.manager.begin_turn()
    speak(env.manager, chunks=2)  # 64 ms: an accidental tap
    env.manager.end_turn()
    await until(lambda: env.rec.dropped == ["short"])
    await asyncio.sleep(0.1)
    assert "activity_start" not in env.server.current.kinds()
    assert "audio" not in env.server.current.kinds()
    assert env.manager.state == LiveState.READY  # the session stays open


async def test_turn_opens_once_enough_audio_arrived(env):
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.manager.begin_turn()
    speak(env.manager, chunks=6)  # 192 ms: still held back
    await asyncio.sleep(0.1)
    assert env.server.current.kinds() == []
    speak(env.manager, chunks=1)  # 224 ms: opens, with the held-back audio in order
    await until(lambda: env.server.current.kinds()[:1] == ["activity_start"])
    await until(lambda: env.server.current.kinds().count("audio") == 7)
    env.manager.end_turn()
    await until(lambda: env.server.current.kinds()[-1:] == ["activity_end"])
    assert env.rec.dropped == []


async def test_short_turn_with_image_is_sent_with_silence(env):
    """Circle to Ask: an image turn is sent even if the question audio is too short; the sender
    adds 32 ms of silence because an activity without audio closes the session (1007)."""
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.manager.begin_turn()
    env.manager.send_image(b"jpeg")
    env.manager.end_turn()
    await until(lambda: "activity_end" in env.server.current.kinds())
    kinds = [k for k in env.server.current.kinds() if k != "video"]
    assert kinds == ["activity_start", "audio", "activity_end"]
    silence = next(v for k, v in env.server.current.sent if k == "audio")
    assert silence.data == session_module.SILENT_CHUNK
    assert "video" in env.server.current.kinds() and env.rec.dropped == []


async def test_cancel_before_open_sends_nothing(env):
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.manager.begin_turn()
    speak(env.manager, chunks=3)
    env.manager.cancel_turn()
    await asyncio.sleep(0.1)
    assert env.server.current.kinds() == [] and env.rec.dropped == []
    assert not env.manager.turn_active


async def test_sender_never_sends_an_empty_activity(env):
    class Recording:
        def __init__(self):
            self.sent = []

        async def send_realtime_input(self, **kwargs):
            self.sent.extend(kwargs)

    session = Recording()
    await env.manager._send_item(session, 1, "activity_start", None)
    await env.manager._send_item(session, 1, "activity_end", None)
    assert session.sent == ["activity_start", "audio", "activity_end"]
    session.sent.clear()
    await env.manager._send_item(session, 1, "activity_start", None)
    await env.manager._send_item(session, 1, "audio", SPEECH_CHUNK)
    await env.manager._send_item(session, 1, "activity_end", None)
    assert session.sent == ["activity_start", "audio", "activity_end"]  # no extra silence


def test_precondition_close_reason_is_shown():
    exc = errors.APIError(1007, "Precondition check failed.")
    kind, message = classify_error(exc, used_handle=False)
    assert kind == "fatal"
    assert "Precondition check failed" in message and "None" not in message
    assert classify_error(exc, used_handle=True)[0] == "resume"


async def test_silent_turn_is_not_sent_and_explained(env):
    """Silence makes the transcriber invent phrases in random languages ("¿Qué?"), so a turn
    without speech never reaches Gemini (D-039)."""
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.manager.begin_turn()
    for _ in range(40):  # 1.3 s of a quiet room
        env.manager.push_audio(QUIET_CHUNK)
    env.manager.end_turn()
    await until(lambda: env.rec.dropped == ["silent"])
    await asyncio.sleep(0.1)
    assert env.server.current.kinds() == []


async def test_a_mic_that_delivers_nothing_is_reported_as_such(env):
    """Digital silence isn't a quiet room: the mic is blocked, muted or the wrong one, and the
    message names the Windows setting to check (D-055)."""
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.manager.begin_turn()
    for _ in range(40):  # 1.3 s of zeros
        env.manager.push_audio(SILENT_CHUNK)
    env.manager.end_turn()
    await until(lambda: env.rec.dropped == ["mic_silent"])
    await asyncio.sleep(0.1)
    assert env.server.current.kinds() == []


async def test_speech_after_a_pause_sends_everything_in_order(env):
    env.manager.connect()
    await until(lambda: env.manager.state == LiveState.READY)
    env.manager.begin_turn()
    for _ in range(5):
        env.manager.push_audio(SILENT_CHUNK)  # the user pauses before speaking
    await asyncio.sleep(0.1)
    assert env.server.current.kinds() == []
    speak(env.manager, chunks=7)
    env.manager.end_turn()
    await until(lambda: "activity_end" in env.server.current.kinds())
    audio = [v.data for k, v in env.server.current.sent if k == "audio"]
    assert audio == [SILENT_CHUNK] * 5 + [SPEECH_CHUNK] * 7


async def test_user_words_stay_on_one_row_per_turn(env):
    def rule(session, kind, value):
        if kind != "activity_end":
            return None
        return [transcript_msg(user="What time"), transcript_msg(model="It's"),
                transcript_msg(user=" is it?"), transcript_msg(model="It's 3 pm."),
                turn_complete()]

    env.server.rules.append(rule)
    env.manager.begin_turn()
    speak(env.manager)
    env.manager.end_turn()
    await until(lambda: any(final for _, _, final in env.rec.user_rows))
    turns = {turn for turn, _, _ in env.rec.user_rows}
    assert turns == {1}  # late words after the answer started still belong to turn 1
    assert env.rec.user_rows[-1] == (1, "What time is it?", True)
    env.rec.user_rows.clear()
    env.manager.begin_turn()
    speak(env.manager)
    env.manager.end_turn()
    await until(lambda: any(final for _, _, final in env.rec.user_rows))
    assert {turn for turn, _, _ in env.rec.user_rows} == {2}


def test_error_detail_lists_type_code_and_reason():
    from wisp.live.session import error_detail

    detail = error_detail(errors.APIError(1008, "API key not valid. Please pass a valid API key."))
    assert detail.startswith("APIError") and "code=1008" in detail and "API key not valid" in detail


def test_bad_key_close_reason_gives_the_key_message():
    """Observed against the real API (2026-10-13): a bad key closes the Live socket with 1007
    and the reason "API key not valid. Please pass a valid API key."."""
    exc = errors.APIError(1007, "API key not valid. Please pass a valid API key.")
    kind, message = classify_error(exc, used_handle=False)
    assert kind == "fatal" and message.startswith("Google rejected this API key")
