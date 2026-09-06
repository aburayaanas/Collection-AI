"""
Runtime Path Resolution.

Centralizes every filesystem location the application touches, and draws a
hard line between two kinds of paths:

- **Resource paths** — read-only files shipped *with* the application
  (SQL feature files, the LLM system prompt). In dev these live under
  ``src/...``; when frozen by PyInstaller they are bundled into the
  onefile executable's temp extraction dir (``sys._MEIPASS``).

- **App-data paths** — mutable state the application reads/writes at
  runtime (``.env``, ``schedule.json``, trained models, score caches,
  logs, MLflow runs). These must live in one fixed, writable location
  that both executables (Service + Configuration GUI) agree on
  regardless of where each was installed or launched from — critical
  once running as a Windows Service, whose working directory is
  ``C:\\Windows\\System32``, not the install folder.

Without this split, a PyInstaller onefile build silently writes into its
own ephemeral extraction folder (resources) or an unpredictable CWD
(app data) — both wrong for a long-running service.
"""

import os
import sys
from pathlib import Path

# Repository root in dev == parent of `src/`. This file lives at
# src/core/paths.py, so parents[2] is the repo root.
_DEV_REPO_ROOT = Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    """True when running from a PyInstaller-built executable."""
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts: str) -> Path:
    """
    Resolve a path to a read-only bundled resource (SQL files, prompt
    templates, etc.), given path components relative to the repo root
    e.g. resource_path("src", "explainability", "llm_system_prompt.md").
    """
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", _DEV_REPO_ROOT))
    else:
        base = _DEV_REPO_ROOT
    return base.joinpath(*parts)


def get_app_dir() -> Path:
    """
    Fixed, writable root for all mutable application state.

    - Frozen: ``%PROGRAMDATA%\\CollectionAI`` (shared machine-wide location,
      independent of where each exe happens to be installed).
    - Dev: the repository root, preserving today's local-dev layout.
    - Either can be overridden with the ``COLLECTIONAI_HOME`` environment
      variable (useful for tests, or to relocate app data deliberately).
    """
    override = os.environ.get("COLLECTIONAI_HOME")
    if override:
        base = Path(override)
    elif is_frozen():
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        base = Path(program_data) / "CollectionAI"
    else:
        base = _DEV_REPO_ROOT
    base.mkdir(parents=True, exist_ok=True)
    return base


APP_DIR = get_app_dir()

ENV_PATH = APP_DIR / ".env"
SCHEDULE_PATH = APP_DIR / "schedule.json"
STATUS_PATH = APP_DIR / "status.json"
RUN_NOW_FLAG_PATH = APP_DIR / "run_now.flag"

MODELS_DIR = APP_DIR / "models"
CACHE_DIR = APP_DIR / "data" / "cache"
LOGS_DIR = APP_DIR / "logs"
MLRUNS_DIR = APP_DIR / "mlruns"

for _d in (MODELS_DIR, CACHE_DIR, LOGS_DIR, MLRUNS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# MLflow reads MLFLOW_TRACKING_URI at first use; it defaults to a relative
# "./mlruns" otherwise, which resolves against whatever the process CWD
# happens to be (System32 for a Windows Service). Anchor it here, once,
# before anything imports mlflow. setdefault() lets an operator override
# it explicitly via the environment if they ever need to.
os.environ.setdefault("MLFLOW_TRACKING_URI", MLRUNS_DIR.as_uri())
