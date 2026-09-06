"""
Schedule persistence.

A ``ScheduledJob`` is one configured trigger — e.g. "Morning Refresh,
07:00, every day, SCORE/BOTH" or "Nightly Retrain, 02:00, every day,
FULL/BOTH". Multiple jobs can run at different times of day (or on
different days), each with its own mode/scope, which is what lets a
schedule pair a cheap twice-daily SCORE-only refresh with an expensive
once-a-day TRAIN.

Stored as JSON at ``paths.SCHEDULE_PATH`` — a single shared file that both
executables read/write: the Configuration exe edits it, the Service exe's
scheduler polls it for changes.
"""

import json
import uuid
from typing import List

from pydantic import BaseModel, Field, field_validator

from src.core import paths

VALID_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
VALID_MODES = ("TRAIN", "SCORE", "FULL")
VALID_MODEL_SCOPES = ("WILLINGNESS", "ABILITY", "BOTH")
VALID_SHAP_SCOPES = ("WILLINGNESS", "ABILITY", "BOTH", "NONE")


class ScheduledJob(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Untitled Job"
    enabled: bool = True
    hour: int = Field(ge=0, le=23, default=7)
    minute: int = Field(ge=0, le=59, default=0)
    days: List[str] = Field(default_factory=lambda: list(VALID_DAYS))
    mode: str = "SCORE"
    model_scope: str = "BOTH"
    shap_scope: str = "BOTH"

    @field_validator("days")
    @classmethod
    def _validate_days(cls, v: List[str]) -> List[str]:
        v = [d.lower() for d in v]
        invalid = set(v) - set(VALID_DAYS)
        if invalid:
            raise ValueError(f"Invalid day(s): {sorted(invalid)}. Must be from {VALID_DAYS}.")
        if not v:
            raise ValueError("At least one day must be selected.")
        return v

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: str) -> str:
        v = v.upper()
        if v not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got {v!r}")
        return v

    @field_validator("model_scope")
    @classmethod
    def _validate_model_scope(cls, v: str) -> str:
        v = v.upper()
        if v not in VALID_MODEL_SCOPES:
            raise ValueError(f"model_scope must be one of {VALID_MODEL_SCOPES}, got {v!r}")
        return v

    @field_validator("shap_scope")
    @classmethod
    def _validate_shap_scope(cls, v: str) -> str:
        v = v.upper()
        if v not in VALID_SHAP_SCOPES:
            raise ValueError(f"shap_scope must be one of {VALID_SHAP_SCOPES}, got {v!r}")
        return v

    def cron_day_of_week(self) -> str:
        """APScheduler CronTrigger day_of_week expression for this job's days."""
        if set(self.days) == set(VALID_DAYS):
            return "*"
        return ",".join(self.days)

    def time_label(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"

    def days_label(self) -> str:
        if set(self.days) == set(VALID_DAYS):
            return "Every day"
        weekdays = {"mon", "tue", "wed", "thu", "fri"}
        if set(self.days) == weekdays:
            return "Weekdays"
        return ", ".join(d.capitalize() for d in VALID_DAYS if d in self.days)


def load_jobs() -> List[ScheduledJob]:
    """Read all jobs from disk. Corrupt/invalid entries are skipped, never fatal."""
    if not paths.SCHEDULE_PATH.exists():
        return []
    try:
        raw = json.loads(paths.SCHEDULE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    jobs: List[ScheduledJob] = []
    for entry in raw.get("jobs", []):
        try:
            jobs.append(ScheduledJob(**entry))
        except Exception:
            continue
    return jobs


def save_jobs(jobs: List[ScheduledJob]) -> None:
    """Atomic write (temp file + replace) so a reader never sees a half-written file."""
    payload = {"jobs": [j.model_dump() for j in jobs]}
    tmp_path = paths.SCHEDULE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(paths.SCHEDULE_PATH)
