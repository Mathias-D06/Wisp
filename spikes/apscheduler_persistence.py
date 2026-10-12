"""Spike: APScheduler 3.11 + SQLAlchemyJobStore (SQLAlchemy 2.1) persistence and misfires.

1. Add two date jobs (textual func reference) to a SQLite store, shut down before they fire.
2. Restart after their run time: the job with a large misfire_grace_time runs late; the one with
   a tiny grace time is reported through EVENT_JOB_MISSED.
Run: .venv\\Scripts\\python spikes\\apscheduler_persistence.py
"""

import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from _aps_job import RAN
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler


def make(db: Path) -> BackgroundScheduler:
    return BackgroundScheduler(jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{db}")},
                               job_defaults={"coalesce": True})


db = Path(tempfile.mkdtemp()) / "jobs.sqlite3"
first = make(db)
first.start(paused=True)
soon = datetime.now().astimezone() + timedelta(seconds=1)
first.add_job("_aps_job:job", "date", run_date=soon, args=["late-ok"],
              id="a", misfire_grace_time=3600, replace_existing=True)
first.add_job("_aps_job:job", "date", run_date=soon, args=["too-late"],
              id="b", misfire_grace_time=1, replace_existing=True)
print("stored jobs:", [j.id for j in first.get_jobs()])
first.shutdown(wait=False)

time.sleep(3)  # "app closed" past the run time
events = []
second = make(db)
second.add_listener(lambda e: events.append((e.code, e.job_id)),
                    EVENT_JOB_EXECUTED | EVENT_JOB_MISSED)
second.start()
time.sleep(1.5)
second.shutdown()
print("ran:", RAN)
print("events:", [("executed" if c == EVENT_JOB_EXECUTED else "missed", j) for c, j in events])
