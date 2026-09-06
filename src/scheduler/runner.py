"""
Run-status tracking, shared by both executables: the Service writes to
paths.STATUS_PATH (see src/scheduler/executor.py) and the Configuration
app reads it via get_status() to show "last run" / "run history" without
tailing raw log files.

Deliberately kept free of any import of src.main (and everything heavy it
pulls in — XGBoost, scikit-learn, MLflow, Polars, Oracle...): PyInstaller's
static analysis bundles every module textually reachable from an entry
script, deferred imports included, so if this file imported src.main the
Configuration exe would drag in the entire ML stack it never actually
runs. That import lives in executor.py instead, which only the Service
exe's entry point reaches.
"""

import json
import threading

from src.core import paths

_status_lock = threading.Lock()
MAX_HISTORY = 20


def read_status() -> dict:
    if not paths.STATUS_PATH.exists():
        return {"current": None, "last": None, "history": []}
    try:
        return json.loads(paths.STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"current": None, "last": None, "history": []}


def write_status(status: dict) -> None:
    tmp_path = paths.STATUS_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
    tmp_path.replace(paths.STATUS_PATH)


def get_status() -> dict:
    """Read-only accessor for the Configuration app's status view."""
    with _status_lock:
        return read_status()


def status_lock() -> threading.Lock:
    return _status_lock
