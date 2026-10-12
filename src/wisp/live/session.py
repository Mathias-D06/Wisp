"""Live session manager: one long conversation over many short connections.

Documented limits this handles (ai.google.dev/gemini-api/docs/live-api/session-management):
* a connection lasts ~10 minutes and the server sends GoAway (``time_left``) before closing it;
* session resumption: the server sends ``session_resumption_update.new_handle`` while the
  session is resumable; reconnecting with that handle keeps the conversation (valid 2 hours);
* context window compression (sliding window) lifts the 15-minute audio session limit.

Behaviour:
* GoAway → reconnect with the latest handle as soon as nothing is in flight (or 1 s before the
  deadline) — invisible to the user apart from a short status blip.
* Network errors → exponential backoff (1, 2, 4 … 30 s) with a clear status; recovers by itself.
* Idle for the configured timeout → close the connection but keep the handle; the next request
  reconnects and resumes.
* Barge-in: starting a turn clears playback locally at once; server ``interrupted`` does too.

All private methods run on the core asyncio loop. Public methods are thread-safe.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from google.genai import types

from wisp.ai.gemini import NO_KEY_MESSAGE, describe_error
from wisp.audio import INPUT_MIME
from wisp.tools.base import Origin

log = logging.getLogger(__name__)


class LiveState(StrEnum):
    IDLE = "idle"
    CONNECTING = "connecting"
    READY = "ready"
    RECONNECTING = "reconnecting"
    OFFLINE = "offline"
    NO_KEY = "no_key"
    ERROR = "error"


def _noop(*_args: Any) -> None:
    return None


@dataclass
class LiveCallbacks:
    state: Callable[[LiveState, str], None] = _noop
    user_text: Callable[[str, bool], None] = _noop
    user_final: Callable[[str], None] = _noop
    model_text: Callable[[str, bool], None] = _noop
    model_audio: Callable[[bytes], None] = _noop
    interrupted: Callable[[], None] = _noop
    turn_complete: Callable[[], None] = _noop
    tool_activity: Callable[[str, str], None] = _noop


def parse_duration(value: str | None) -> float:
    """Protobuf JSON duration such as '12.5s' → seconds."""
    if not value:
        return 0.0
    match = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)s\s*", value)
    return float(match.group(1)) if match else 0.0


def classify_error(exc: BaseException, used_handle: bool) -> tuple[str, str]:
    """Return (kind, message): kind is 'fatal', 'resume' (drop handle, retry now) or 'retry'."""
    from google.genai import errors

    if isinstance(exc, PermissionError):
        return "fatal", NO_KEY_MESSAGE
    if isinstance(exc, errors.APIError):
        code = exc.code or 0
        text = f"{exc.status or ''} {exc.message or ''}".lower()
        if code in (401, 403) or "api key" in text or "api_key" in text or "billing" in text:
            return "fatal", describe_error(exc)
        if code == 404:
            return "fatal", describe_error(exc)
        if code in (400, 1007, 1008):
            if used_handle:
                return "resume", "Previous conversation could not be resumed; starting fresh."
            return "fatal", f"The voice session was rejected: {exc.message or exc.status}"
        if code == 429:
            return "retry", "Quota or rate limit reached."
        return "retry", "Connection to Gemini lost."
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return "fatal", "Google rejected the API key for the voice session."
    if status == 404:
        return "fatal", "The configured Live model was not found. Check Settings → General."
    if isinstance(exc, OSError | TimeoutError | EOFError) or "websockets" in type(exc).__module__:
        return "retry", "Can't reach Google. Check your internet connection."
    return "retry", f"Voice session error ({type(exc).__name__})."


class LiveSessionManager:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        connector,
        config_factory: Callable[[str | None], Any],
        dispatcher,
        callbacks: LiveCallbacks,
        *,
        has_key: Callable[[], bool],
        idle_timeout_s: Callable[[], float],
        always_listening: Callable[[], bool],
        is_playing: Callable[[], bool] = lambda: False,
        extended_thinking: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
        tick_s: float = 1.0,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
        max_audio_backlog: int = 470,
    ):
        self._loop = loop
        self._connector = connector
        self._config_factory = config_factory
        self._dispatcher = dispatcher
        self._cb = callbacks
        self._has_key = has_key
        self._idle_timeout_s = idle_timeout_s
        self._always_listening = always_listening
        self._is_playing = is_playing
        self._extended_thinking = extended_thinking
        self._clock = clock
        self._tick = tick_s
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._max_audio = max_audio_backlog

        self.state = LiveState.IDLE
        self.state_detail = ""
        self.handle: str | None = None
        self._wanted = False
        self._runner: asyncio.Task | None = None
        self._out: collections.deque[tuple[str, Any]] = collections.deque()
        self._out_event = asyncio.Event()
        self._wake = asyncio.Event()
        self._conn_id = 0
        self._turn_active = False
        self._activity_open = False
        self._suppress_audio = False
        self._pending_tools = 0
        self._tool_tasks: set[asyncio.Task] = set()
        self._cancelled: set[str] = set()
        self._model_generating = False
        self._reconnect_requested = False
        self._go_away_deadline: float | None = None
        self._user_text = ""
        self._model_text = ""
        self._last_activity = clock()
        self.connections_opened = 0

    # ----- thread-safe API -------------------------------------------------------------------
    def _call(self, fn: Callable[..., Any], *args: Any) -> None:
        self._loop.call_soon_threadsafe(fn, *args)

    def connect(self) -> None:
        self._call(self._want)

    def begin_turn(self) -> None:
        self._call(self._begin_turn)

    def push_audio(self, pcm: bytes) -> None:
        self._call(self._push_audio, pcm)

    def end_turn(self) -> None:
        self._call(self._end_turn)

    def cancel_turn(self) -> None:
        self._call(self._cancel_turn)

    def send_text(self, text: str) -> None:
        self._call(self._send, "text", text)

    def send_image(self, jpeg: bytes) -> None:
        self._call(self._send, "video", jpeg)

    def audio_stream_end(self) -> None:
        self._call(self._send, "audio_stream_end", None)

    def request_reconnect(self) -> None:
        self._call(self._request_reconnect)

    def disconnect(self) -> None:
        self._call(self._stop)

    @property
    def turn_active(self) -> bool:
        return self._turn_active

    def has_key(self) -> bool:
        return bool(self._has_key())

    # ----- loop-thread internals -------------------------------------------------------------
    def _set_state(self, state: LiveState, detail: str) -> None:
        if state != self.state or detail != self.state_detail:
            self.state, self.state_detail = state, detail
            log.info("Live state %s: %s", state.value, detail)
            self._cb.state(state, detail)

    def _touch(self) -> None:
        self._last_activity = self._clock()

    def _want(self) -> None:
        self._touch()
        if not self._has_key():
            self._set_state(LiveState.NO_KEY, NO_KEY_MESSAGE)
            return
        self._wanted = True
        if self._runner is None or self._runner.done():
            self._runner = self._loop.create_task(self._connection_loop())
        else:
            self._wake.set()

    def _begin_turn(self) -> None:
        self._want()
        if not self._wanted:
            return
        self._cb.interrupted()  # barge-in: stop speaking immediately
        self._suppress_audio = True
        self._turn_active = True
        self._user_text = ""
        if not self._always_listening():
            self._enqueue(("activity_start", None))

    def _push_audio(self, pcm: bytes) -> None:
        if self._turn_active or (self._always_listening() and self._wanted):
            self._enqueue(("audio", pcm))

    def _end_turn(self) -> None:
        if not self._turn_active:
            return
        self._turn_active = False
        self._suppress_audio = False
        self._touch()
        if not self._always_listening():
            self._enqueue(("activity_end", None))

    def _cancel_turn(self) -> None:
        """Abandon a turn (e.g. another key was pressed): drop its queued audio, close it."""
        if not self._turn_active:
            return
        self._out = collections.deque(i for i in self._out if i[0] != "audio")
        self._end_turn()

    def _send(self, kind: str, payload: Any) -> None:
        self._want()
        if self._wanted:
            self._enqueue((kind, payload))

    def _request_reconnect(self) -> None:
        if self._runner is not None and not self._runner.done():
            self._reconnect_requested = True

    def _stop(self) -> None:
        self._wanted = False
        self._out.clear()
        self._wake.set()
        if self._runner is not None and not self._runner.done():
            self._runner.cancel()
        self._set_state(LiveState.IDLE, "Disconnected")

    def _enqueue(self, item: tuple[str, Any], front: bool = False) -> None:
        if front:
            self._out.appendleft(item)
        else:
            self._out.append(item)
        if item[0] == "audio":
            audio = sum(1 for kind, _ in self._out if kind == "audio")
            while audio > self._max_audio:
                for index, (kind, _payload) in enumerate(self._out):
                    if kind == "audio":
                        del self._out[index]
                        audio -= 1
                        break
        self._out_event.set()

    async def _connection_loop(self) -> None:
        attempt = 0
        try:
            while self._wanted:
                if not self._has_key():
                    self._set_state(LiveState.NO_KEY, NO_KEY_MESSAGE)
                    self._wanted = False
                    break
                resuming = self.handle is not None and self.connections_opened > 0
                self._set_state(
                    LiveState.RECONNECTING if (attempt or resuming) else LiveState.CONNECTING,
                    "Reconnecting…" if (attempt or resuming) else "Connecting…",
                )
                used_handle = self.handle is not None
                try:
                    config = self._config_factory(self.handle)
                    async with self._connector.connect(config) as session:
                        attempt = 0
                        reason = await self._run_connection(session)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    kind, message = classify_error(exc, used_handle)
                    if self._reconnect_requested or self._go_away_deadline is not None:
                        # The server ended the connection after GoAway: just reconnect.
                        log.info("Connection ended after GoAway/reconnect request (%s)", exc)
                        self._reconnect_requested = False
                        self._go_away_deadline = None
                        continue
                    log.warning("Live connection error (%s): %s", kind, exc)
                    if kind == "fatal":
                        self._wanted = False
                        self._out.clear()
                        self._set_state(LiveState.ERROR, message)
                        break
                    if kind == "resume":
                        self.handle = None
                        self._cb.state(LiveState.RECONNECTING, message)
                        continue
                    attempt += 1
                    delay = min(self._backoff_max, self._backoff_base * 2 ** (attempt - 1))
                    self._set_state(LiveState.OFFLINE, f"{message} Retrying in {delay:.0f} s…")
                    await self._sleep(delay)
                    continue
                if reason == "idle":
                    self._wanted = False
                    self._set_state(LiveState.IDLE, "Idle — will reconnect when you talk")
                    break
        finally:
            if self.state in (LiveState.READY, LiveState.CONNECTING, LiveState.RECONNECTING):
                self._set_state(LiveState.IDLE, "Disconnected")

    async def _sleep(self, delay: float) -> None:
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), delay)
        except TimeoutError:
            return

    async def _run_connection(self, session) -> str:
        self._conn_id += 1
        self.connections_opened += 1
        conn_id = self._conn_id
        self._activity_open = False
        self._reconnect_requested = False
        self._go_away_deadline = None
        self._model_generating = False
        self._touch()
        if self._turn_active and not self._always_listening():
            # Re-open an in-progress push-to-talk turn on the new connection.
            self._out = collections.deque(i for i in self._out if i[0] != "activity_start")
            self._enqueue(("activity_start", None), front=True)
        self._set_state(LiveState.READY, "Connected")
        tasks = {
            asyncio.create_task(self._sender(session, conn_id), name="live-send"),
            asyncio.create_task(self._receiver(session), name="live-recv"),
            asyncio.create_task(self._watchdog(), name="live-watch"),
        }
        try:
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None:
                raise exc
            return task.result()
        return "closed"

    async def _sender(self, session, conn_id: int) -> str:
        while True:
            while not self._out:
                self._out_event.clear()
                await self._out_event.wait()
            kind, payload = self._out.popleft()
            try:
                await self._send_item(session, conn_id, kind, payload)
            except Exception:
                self._enqueue((kind, payload), front=True)
                raise

    async def _send_item(self, session, conn_id: int, kind: str, payload: Any) -> None:
        manual = not self._always_listening()
        if kind == "activity_start":
            if manual and not self._activity_open:
                await session.send_realtime_input(activity_start=types.ActivityStart())
                self._activity_open = True
        elif kind == "activity_end":
            if manual and self._activity_open:
                await session.send_realtime_input(activity_end=types.ActivityEnd())
                self._activity_open = False
        elif kind == "audio":
            if manual and not self._activity_open:
                return  # audio outside a turn is dropped in push-to-talk mode
            await session.send_realtime_input(audio=types.Blob(data=payload, mime_type=INPUT_MIME))
        elif kind == "text":
            self._touch()
            await session.send_realtime_input(text=payload)
        elif kind == "video":
            self._touch()
            frame = types.Blob(data=payload, mime_type="image/jpeg")
            await session.send_realtime_input(video=frame)
        elif kind == "audio_stream_end":
            if not manual:
                await session.send_realtime_input(audio_stream_end=True)
        elif kind == "tool_response":
            call_conn, responses = payload
            if call_conn == conn_id:
                await session.send_tool_response(function_responses=responses)
            else:
                # The calls belonged to a previous connection; report results as context.
                summary = "; ".join(f"{r.name}: {r.response}" for r in responses)[:2000]
                await session.send_realtime_input(
                    text=f"[Wisp notice] Results of actions from before the reconnect: {summary}"
                )
        else:
            log.error("Unknown outgoing item %s", kind)

    async def _receiver(self, session) -> str:
        while True:
            async for message in session.receive():
                await self._on_message(message)

    async def _watchdog(self) -> str:
        while True:
            await asyncio.sleep(self._tick)
            now = self._clock()
            if self._go_away_deadline is not None and now >= self._go_away_deadline:
                log.info("GoAway deadline reached; reconnecting")
                return "go_away"
            if self._reconnect_requested and self._quiet():
                return "reconnect"
            if self._quiet() and now - self._last_activity > self._idle_timeout_s():
                return "idle"

    def _quiet(self) -> bool:
        return (
            not self._turn_active
            and self._pending_tools == 0
            and not self._model_generating
            and not self._out
            and not self._is_playing()
        )

    # ----- incoming messages -----------------------------------------------------------------
    async def _on_message(self, message: types.LiveServerMessage) -> None:
        if message.session_resumption_update is not None:
            update = message.session_resumption_update
            if update.resumable and update.new_handle:
                self.handle = update.new_handle
        if message.go_away is not None:
            left = parse_duration(message.go_away.time_left)
            self._go_away_deadline = self._clock() + max(0.0, left - 1.0)
            self._reconnect_requested = True
            log.info("GoAway received (%.1f s left)", left)
        content = message.server_content
        if content is not None:
            self._on_content(content)
        if message.tool_call is not None:
            self._model_generating = False
            self._flush_user_text()
            self._pending_tools += 1
            task = asyncio.create_task(self._run_tools(message.tool_call, self._conn_id))
            self._tool_tasks.add(task)  # keep a strong reference until it finishes
            task.add_done_callback(self._tool_tasks.discard)
        if message.tool_call_cancellation is not None:
            self._cancelled.update(message.tool_call_cancellation.ids or [])
        if message.usage_metadata is not None:
            log.debug("Usage: %s", message.usage_metadata.total_token_count)

    def _on_content(self, content: types.LiveServerContent) -> None:
        if content.input_transcription is not None and content.input_transcription.text:
            self._touch()
            self._user_text += content.input_transcription.text
            self._cb.user_text(self._user_text, False)
            if content.input_transcription.finished:
                self._flush_user_text()
        if content.interrupted:
            self._model_generating = False
            self._cb.interrupted()
            self._finish_model_text()
        if content.model_turn is not None and content.model_turn.parts:
            self._flush_user_text()
            for part in content.model_turn.parts:
                if part.inline_data is not None and part.inline_data.data:
                    self._touch()
                    if not self._suppress_audio:
                        self._model_generating = True
                        self._cb.model_audio(part.inline_data.data)
        if content.output_transcription is not None and content.output_transcription.text:
            self._flush_user_text()
            self._touch()
            if not self._suppress_audio:
                self._model_text += content.output_transcription.text
                self._cb.model_text(self._model_text, False)
        if content.turn_complete:
            self._model_generating = False
            self._flush_user_text()
            self._finish_model_text()
            self._cb.turn_complete()
            self._touch()

    def _flush_user_text(self) -> None:
        if self._user_text.strip():
            text, self._user_text = self._user_text.strip(), ""
            self._cb.user_text(text, True)
            self._cb.user_final(text)

    def _finish_model_text(self) -> None:
        if self._model_text.strip():
            self._cb.model_text(self._model_text.strip(), True)
        self._model_text = ""

    async def _run_tools(self, tool_call: types.LiveServerToolCall, conn_id: int) -> None:
        try:
            responses = []
            for call in tool_call.function_calls or []:
                if call.id in self._cancelled:
                    continue
                name = call.name or ""
                self._cb.tool_activity(name, "start")
                try:
                    result = await self._dispatcher.dispatch(
                        name, call.args or {}, Origin.VOICE, call_id=call.id
                    )
                finally:
                    self._cb.tool_activity(name, "end")
                if call.id in self._cancelled:
                    continue
                response = types.FunctionResponse(id=call.id, name=name, response=result)
                if self._extended_thinking():
                    response.scheduling = types.FunctionResponseScheduling.WHEN_IDLE
                responses.append(response)
            if responses:
                self._enqueue(("tool_response", (conn_id, responses)), front=True)
        except Exception:
            log.exception("Tool call handling failed")
        finally:
            self._pending_tools -= 1
            self._touch()
