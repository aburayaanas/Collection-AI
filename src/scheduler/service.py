"""
Scheduler core.

Builds an APScheduler ``BackgroundScheduler`` from ``schedule.json`` and
keeps it in sync with two things an operator can change at any time
without restarting the Windows Service:

- ``schedule.json`` — edited by the Configuration app's Schedule tab.
- ``.env``          — edited by the Configuration app's other tabs.

A lightweight watcher job polls both files' mtimes every
``WATCH_INTERVAL_SECONDS`` and a "run now" flag file the Configuration
app can drop to trigger an immediate one-off run. This file-polling is
the *only* IPC between the two executables, deliberately — no sockets,
no ports, nothing that needs its own firewall rule or admin-only named
pipe.

Every scheduled trigger gets ``max_instances=1`` + ``coalesce=True`` so
a pipeline run that's still going when its next trigger fires is never
started twice in parallel (which would double-write to the DB and can
exhaust the Oracle connection pool), and a ``misfire_grace_time`` so a
trigger missed while the machine was asleep/off still fires once it's
back, instead of silently vanishing.
"""

import json
import logging
import time
from typing import Optional, Set

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core import paths
from src.core.config import reload_settings
from src.scheduler.jobstore import ScheduledJob, load_jobs
from src.scheduler.executor import run_job

logger = logging.getLogger(__name__)

WATCH_INTERVAL_SECONDS = 15
MISFIRE_GRACE_SECONDS = 3600  # tolerate up to 1h delay (sleep/reboot) before skipping a run


class SchedulerService:
    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler()  # defaults to the system's local timezone
        self._schedule_mtime: Optional[float] = None
        self._env_mtime: Optional[float] = None
        self._job_ids: Set[str] = set()

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        self._reload_env(force=True)
        self._reload_jobs(force=True)
        self._scheduler.add_job(
            self._watch,
            "interval",
            seconds=WATCH_INTERVAL_SECONDS,
            id="__watcher__",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info("Scheduler started.")

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")

    # ── watcher: config hot-reload + run-now flag ───────────────────

    def _watch(self) -> None:
        self._reload_env()
        self._reload_jobs()
        self._check_run_now_flag()

    def _reload_env(self, force: bool = False) -> None:
        if not paths.ENV_PATH.exists():
            return
        mtime = paths.ENV_PATH.stat().st_mtime
        if force or mtime != self._env_mtime:
            reload_settings()
            self._env_mtime = mtime
            if not force:
                logger.info("Detected .env change — configuration reloaded.")

    def _reload_jobs(self, force: bool = False) -> None:
        if not paths.SCHEDULE_PATH.exists():
            if force:
                self._schedule_mtime = None
            return
        mtime = paths.SCHEDULE_PATH.stat().st_mtime
        if not force and mtime == self._schedule_mtime:
            return
        self._schedule_mtime = mtime

        jobs = load_jobs()
        self._apply_jobs(jobs)
        if not force:
            logger.info(f"Detected schedule.json change — {len(jobs)} job(s) reloaded.")

    def _apply_jobs(self, jobs) -> None:
        desired_ids = {j.id for j in jobs if j.enabled}
        for stale_id in self._job_ids - desired_ids:
            try:
                self._scheduler.remove_job(stale_id)
            except Exception:
                pass

        self._job_ids = set()
        for job in jobs:
            if not job.enabled:
                continue
            trigger = CronTrigger(
                hour=job.hour,
                minute=job.minute,
                day_of_week=job.cron_day_of_week(),
            )
            self._scheduler.add_job(
                run_job,
                trigger=trigger,
                args=[job, "schedule"],
                id=job.id,
                name=job.name,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=MISFIRE_GRACE_SECONDS,
            )
            self._job_ids.add(job.id)

        logger.info(f"Active scheduled jobs: {sorted(self._job_ids)}")

    def _check_run_now_flag(self) -> None:
        if not paths.RUN_NOW_FLAG_PATH.exists():
            return
        try:
            payload = json.loads(paths.RUN_NOW_FLAG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        finally:
            try:
                paths.RUN_NOW_FLAG_PATH.unlink()
            except OSError:
                pass

        job = ScheduledJob(
            id=f"manual-{int(time.time())}",
            name=payload.get("name", "Manual Run"),
            enabled=True,
            hour=0,
            minute=0,
            mode=payload.get("mode", "SCORE"),
            model_scope=payload.get("model_scope", "BOTH"),
            shap_scope=payload.get("shap_scope", "BOTH"),
        )
        logger.info(f"Run-now flag detected — queuing manual job '{job.name}'.")
        # Queue it as its own one-off APScheduler job so it runs on the
        # scheduler's worker pool instead of blocking this watcher tick.
        self._scheduler.add_job(run_job, args=[job, "manual"], id=job.id)
