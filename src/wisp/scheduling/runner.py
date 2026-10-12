"""Entry point stored in the persistent job store as ``wisp.scheduling.runner:run_scheduled_task``.

APScheduler 3.x persists jobs by textual reference ("package.module:callable") and pickled
arguments, so the job only stores the task id; the running app installs the handler.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

JOB_REFERENCE = "wisp.scheduling.runner:run_scheduled_task"

_handler: Callable[[str], None] | None = None


def set_handler(handler: Callable[[str], None] | None) -> None:
    global _handler
    _handler = handler


def run_scheduled_task(task_id: str) -> None:
    if _handler is None:
        log.warning("Scheduled task %s fired before the app was ready", task_id)
        return
    _handler(task_id)
