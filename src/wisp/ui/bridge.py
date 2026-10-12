"""Run callables on the Qt UI thread from any thread and get a Future back."""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal


class UiInvoker(QObject):
    _request = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._request.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def call(self, fn: Callable[[], Any]) -> concurrent.futures.Future:
        future: concurrent.futures.Future = concurrent.futures.Future()
        if QThread.currentThread() is self.thread():
            self._execute(fn, future)
        else:
            self._request.emit((fn, future))
        return future

    def call_sync(self, fn: Callable[[], Any], timeout: float = 30.0) -> Any:
        return self.call(fn).result(timeout)

    def _run(self, payload: tuple[Callable[[], Any], concurrent.futures.Future]) -> None:
        fn, future = payload
        self._execute(fn, future)

    @staticmethod
    def _execute(fn: Callable[[], Any], future: concurrent.futures.Future) -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(fn())
        except BaseException as exc:
            future.set_exception(exc)
