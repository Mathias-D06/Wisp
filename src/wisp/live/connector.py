"""Opens Live API connections. Tests substitute a fake connector with the same shape."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol


class LiveSessionLike(Protocol):
    async def send_realtime_input(self, **kwargs: Any) -> None: ...
    async def send_tool_response(self, *, function_responses: Any) -> None: ...
    def receive(self) -> Any: ...


class Connector(Protocol):
    def connect(self, config: Any) -> AbstractAsyncContextManager[LiveSessionLike]: ...


class GenaiConnector:
    """``client.aio.live.connect(model=, config=)`` from the official SDK."""

    def __init__(self, api_key: Callable[[], str | None], model: Callable[[], str]):
        self._api_key = api_key
        self._model = model
        self._client = None
        self._client_key: str | None = None

    def _get_client(self):
        key = self._api_key()
        if not key:
            raise PermissionError("No API key")
        if self._client is None or self._client_key != key:
            from google import genai

            self._client = genai.Client(api_key=key)
            self._client_key = key
        return self._client

    def connect(self, config: Any) -> AbstractAsyncContextManager[LiveSessionLike]:
        return self._get_client().aio.live.connect(model=self._model(), config=config)
