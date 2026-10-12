"""The core asyncio loop, running on its own thread beside the Qt UI thread."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any

log = logging.getLogger(__name__)


class LoopThread:
    def __init__(self, name: str = "core-loop"):
        self.loop = asyncio.new_event_loop()
        self.loop.set_exception_handler(self._on_exception)
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call_soon(self, fn: Callable[..., Any], *args: Any) -> None:
        self.loop.call_soon_threadsafe(fn, *args)

    def stop(self, timeout: float = 3.0) -> None:
        if not self._thread.is_alive():
            return

        async def _cancel_all() -> None:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        try:
            self.submit(_cancel_all()).result(timeout)
        except Exception as exc:
            log.warning("Stopping loop tasks: %s", exc)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout)

    @staticmethod
    def _on_exception(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        if exc is not None:
            log.error("Unhandled loop error: %s", context.get("message"), exc_info=exc)
        else:
            log.error("Unhandled loop error: %s", context.get("message"))
