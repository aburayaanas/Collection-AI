"""
Executes one pipeline run for a ScheduledJob.

Split out from runner.py specifically so this is the only module in the
scheduler package that imports src.main (and the full ML stack it pulls
in). Only the Service exe's entry point (service_app.py ->
src.scheduler.win_service -> src.scheduler.service) reaches this module;
the Configuration exe never does, so its build stays lean.

Deliberately never raises: a scheduler process must survive one job's
failure so it can still fire the next scheduled trigger.
"""

import traceback
from datetime import datetime, timezone

from src.core.config import reload_settings
from src.core.logger import get_logger
from src.core.taxonomy import ErrorAdvisor
from src.scheduler.jobstore import ScheduledJob
from src.scheduler.runner import MAX_HISTORY, read_status, status_lock, write_status

logger = get_logger(__name__)


def run_job(job: ScheduledJob, triggered_by: str = "schedule") -> None:
    """Execute one pipeline run for `job`. Never raises."""
    from src.main import execute_pipeline

    started_at = datetime.now(timezone.utc)
    logger.info(
        f"[{triggered_by}] Running job '{job.name}' ({job.id}) | "
        f"mode={job.mode} scope={job.model_scope}/{job.shap_scope}"
    )

    entry = {
        "job_id": job.id,
        "job_name": job.name,
        "triggered_by": triggered_by,
        "mode": job.mode,
        "model_scope": job.model_scope,
        "shap_scope": job.shap_scope,
        "started_at": started_at.isoformat(),
        "ended_at": None,
        "status": "RUNNING",
        "error": None,
    }
    lock = status_lock()
    with lock:
        status = read_status()
        status["current"] = entry
        write_status(status)

    try:
        reload_settings()
        execute_pipeline(job.mode, job.model_scope, job.shap_scope)
        entry["status"] = "SUCCESS"
    except Exception as e:
        error_text = ErrorAdvisor.analyze(e)
        entry["status"] = "FAILED"
        entry["error"] = error_text
        logger.critical(
            f"Job '{job.name}' ({job.id}) FAILED:\n{error_text}\n{traceback.format_exc()}"
        )
    finally:
        entry["ended_at"] = datetime.now(timezone.utc).isoformat()
        with lock:
            status = read_status()
            status["current"] = None
            status["last"] = entry
            history = status.get("history", [])
            history.insert(0, entry)
            status["history"] = history[:MAX_HISTORY]
            write_status(status)
