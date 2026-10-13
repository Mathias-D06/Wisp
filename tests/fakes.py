"""Test doubles: a fake Live API server that replays scripted messages, plus small helpers.

Messages are built from the Live API's wire JSON with the SDK's own parser
(``types.LiveServerMessage._from_response``), so tests exercise the same objects the real
connection yields.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from google.genai import types


def msg(wire: dict[str, Any]) -> types.LiveServerMessage:
    return types.LiveServerMessage._from_response(response=wire, kwargs={})


def audio_msg(pcm: bytes = b"\x01\x00" * 240) -> types.LiveServerMessage:
    data = base64.b64encode(pcm).decode()
    return msg({"serverContent": {"modelTurn": {"parts": [
        {"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": data}}]}}})


def transcript_msg(user: str | None = None, model: str | None = None,
                   finished: bool = False) -> types.LiveServerMessage:
    content: dict[str, Any] = {}
    if user is not None:
        content["inputTranscription"] = {"text": user, "finished": finished}
    if model is not None:
        content["outputTranscription"] = {"text": model}
    return msg({"serverContent": content})


def turn_complete() -> types.LiveServerMessage:
    return msg({"serverContent": {"turnComplete": True}})


def interrupted() -> types.LiveServerMessage:
    return msg({"serverContent": {"interrupted": True}})


def tool_call(*calls: tuple[str, str, dict[str, Any]]) -> types.LiveServerMessage:
    return msg({"toolCall": {"functionCalls": [
        {"id": cid, "name": name, "args": args} for cid, name, args in calls]}})


def resumption(handle: str, resumable: bool = True) -> types.LiveServerMessage:
    return msg({"sessionResumptionUpdate": {"newHandle": handle, "resumable": resumable}})


def go_away(seconds: float) -> types.LiveServerMessage:
    return msg({"goAway": {"timeLeft": f"{seconds}s"}})


class FakeSession:
    def __init__(self, server: FakeLiveServer, config: Any):
        self.server = server
        self.config = config
        self.sent: list[tuple[str, Any]] = []
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.closed = False

    @property
    def handle(self) -> str | None:
        resumption_config = getattr(self.config, "session_resumption", None)
        return resumption_config.handle if resumption_config else None

    async def send_realtime_input(self, **kwargs: Any) -> None:
        (key, value), = kwargs.items()
        self.sent.append((key, value))
        self.server.react(self, key, value)

    async def send_tool_response(self, *, function_responses: Any) -> None:
        responses = function_responses if isinstance(function_responses, list) else [
            function_responses]
        self.sent.append(("tool_response", responses))
        self.server.react(self, "tool_response", responses)

    async def receive(self):
        while True:
            item = await self.incoming.get()
            if isinstance(item, BaseException):
                raise item
            yield item
            content = item.server_content
            if content is not None and content.turn_complete:
                return

    def push(self, *messages: Any) -> None:
        for message in messages:
            self.incoming.put_nowait(message)

    def kinds(self) -> list[str]:
        return [k for k, _ in self.sent]


Rule = Callable[[FakeSession, str, Any], list[Any] | None]


class FakeLiveServer:
    """Connector + scripted server. ``rules`` react to what the client sends."""

    def __init__(self) -> None:
        self.sessions: list[FakeSession] = []
        self.configs: list[Any] = []
        self.connect_errors: list[BaseException] = []
        self.rules: list[Rule] = []

    def connect(self, config: Any):
        return self._connect(config)

    @asynccontextmanager
    async def _connect(self, config: Any):
        self.configs.append(config)
        if self.connect_errors:
            raise self.connect_errors.pop(0)
        session = FakeSession(self, config)
        self.sessions.append(session)
        try:
            yield session
        finally:
            session.closed = True

    def react(self, session: FakeSession, kind: str, value: Any) -> None:
        for rule in self.rules:
            out = rule(session, kind, value)
            if out:
                session.push(*out)

    @property
    def current(self) -> FakeSession:
        return self.sessions[-1]


async def until(condition: Callable[[], bool], timeout: float = 3.0, step: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(step)


class DirectUi:
    """Runs 'UI thread' calls inline (tests have no Qt loop)."""

    def call(self, fn: Callable[[], Any]) -> concurrent.futures.Future:
        future: concurrent.futures.Future = concurrent.futures.Future()
        try:
            future.set_result(fn())
        except Exception as exc:
            future.set_exception(exc)
        return future


SPEECH_CHUNK = b"\x01\x00" * 512  # 32 ms of (non-silent) 16 kHz audio


def speak(manager, chunks: int = 10) -> None:
    """Push ~0.32 s of audio into a push-to-talk turn (enough to open it; D-038)."""
    for _ in range(chunks):
        manager.push_audio(SPEECH_CHUNK)
