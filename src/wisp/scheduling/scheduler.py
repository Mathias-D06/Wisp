"""Task scheduler: APScheduler 3.x BackgroundScheduler + SQLAlchemyJobStore (jobs.sqlite3).

Missed-run policy (README "Scheduled tasks"; proven by spikes/apscheduler_persistence.py):
* Jobs persist in SQLite; on start APScheduler checks each missed run time against the job's
  ``misfire_grace_time`` and coalesces several missed runs into one.
* One-off tasks run late if Wisp starts within ``one_off_grace_hours`` (default 12 h) of the
  time; otherwise they are reported as missed and disabled.
* Recurring tasks run once at start-up if the last occurrence was missed by less than
  ``recurring_grace_minutes`` (default 60); older occurrences are skipped and reported.
* After every run (or miss) a notification says what happened.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, tzinfo

from wisp.scheduling import runner
from wisp.scheduling.tasks import Task, TaskStore

log = logging.getLogger(__name__)


def local_tz() -> tzinfo:
    return datetime.now().astimezone().tzinfo


class TaskScheduler:
    def __init__(self, store: TaskStore, jobs_url: str, settings: Callable,
                 execute: Callable[[Task], tuple[bool, str]],
                 notify: Callable[[str, str], None], tz: tzinfo | None = None):
        self.store = store
        self.jobs_url = jobs_url
        self.settings = settings
        self.execute = execute
        self.notify = notify
        self.tz = tz or local_tz()
        self._scheduler = None
        self._missed: list[str] = []
        self._lock = threading.Lock()

    # ----- lifecycle ---------------------------------------------------------------------------
    def start(self) -> None:
        from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.background import BackgroundScheduler

        self._scheduler = BackgroundScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=self.jobs_url)},
            job_defaults={"coalesce": True, "max_instances": 1},
            timezone=self.tz,
        )
        self._scheduler.add_listener(self._on_event, EVENT_JOB_MISSED | EVENT_JOB_ERROR)
        runner.set_handler(self._run)
        self._scheduler.start(paused=True)
        self._sync()
        self._scheduler.resume()
        log.info("Scheduler started with %d jobs", len(self._scheduler.get_jobs()))

    def shutdown(self) -> None:
        runner.set_handler(None)
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _sync(self) -> None:
        """Make the job store match the task table (e.g. after jobs.sqlite3 was deleted)."""
        jobs = {job.id for job in self._scheduler.get_jobs()}
        tasks = {task.id: task for task in self.store.list()}
        for job_id in jobs - set(tasks):
            self._scheduler.remove_job(job_id)
        for task in tasks.values():
            if not task.enabled:
                if task.id in jobs:
                    self._scheduler.remove_job(task.id)
            elif task.id not in jobs and not (task.schedule.one_off and task.last_run_at):
                self._add_job(task)

    # ----- jobs --------------------------------------------------------------------------------
    def grace_seconds(self, task: Task) -> int:
        settings = self.settings().scheduler
        if task.schedule.one_off:
            seconds = settings.one_off_grace_hours * 3600
        else:
            seconds = settings.recurring_grace_minutes * 60
        return max(1, seconds)  # APScheduler needs a positive value; 0 means "never run late"

    def _add_job(self, task: Task) -> None:
        self._scheduler.add_job(
            runner.JOB_REFERENCE, trigger=task.schedule.trigger(self.tz), args=[task.id],
            id=task.id, name=task.title[:200], replace_existing=True,
            misfire_grace_time=self.grace_seconds(task),
        )

    def schedule(self, task: Task) -> None:
        if self._scheduler is None:
            return
        if task.enabled:
            self._add_job(task)
        else:
            self.unschedule(task.id)

    def unschedule(self, task_id: str) -> None:
        if self._scheduler is not None and self._scheduler.get_job(task_id):
            self._scheduler.remove_job(task_id)

    def next_run(self, task_id: str) -> datetime | None:
        if self._scheduler is None:
            return None
        job = self._scheduler.get_job(task_id)
        return job.next_run_time if job else None

    def upcoming(self, limit: int = 10) -> list[tuple[Task, datetime]]:
        result = []
        for task in self.store.list():
            when = self.next_run(task.id)
            if when is not None and task.enabled:
                result.append((task, when))
        result.sort(key=lambda pair: pair[1])
        return result[:limit]

    def run_now(self, task_id: str) -> None:
        threading.Thread(target=self._run, args=(task_id, True), name="task-now",
                         daemon=True).start()

    # ----- execution ---------------------------------------------------------------------------
    def _run(self, task_id: str, manual: bool = False) -> None:
        task = self.store.get(task_id)
        if task is None or (not task.enabled and not manual):
            return
        try:
            ok, summary = self.execute(task)
        except Exception as exc:
            log.exception("Task %s failed", task.title)
            ok, summary = False, f"Failed: {type(exc).__name__}: {exc}"
        self.store.record_run(task.id, summary)
        if task.schedule.one_off and not manual:
            self.store.update(task.id, enabled=False)
        title = f"Routine done: {task.title}" if ok else f"Routine had problems: {task.title}"
        self.notify(title, summary)

    def _on_event(self, event) -> None:
        from apscheduler.events import EVENT_JOB_MISSED

        task = self.store.get(event.job_id)
        if task is None:
            return
        if event.code == EVENT_JOB_MISSED:
            when = event.scheduled_run_time
            stamp = when.strftime("%a %d %b %H:%M") if when else "its run time"
            self.store.record_run(task.id, f"Missed: Wisp wasn't running at {stamp}.")
            if task.schedule.one_off:
                self.store.update(task.id, enabled=False)
            self.notify("Missed while Wisp was closed", f"{task.title} ({stamp})")
        else:
            self.store.record_run(task.id, f"Error: {event.exception}")
