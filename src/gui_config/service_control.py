"""
Service control for the Configuration app's "Service" tab.

Installing/starting/stopping the Windows Service requires Administrator
rights. Rather than reimplementing UAC elevation and service-management
logic here, this shells out to the Service exe itself (it already knows
how to install/start/stop/remove itself via pywin32 — see
src/scheduler/win_service.py) through ShellExecuteW's "runas" verb, which
pops the standard Windows elevation prompt.
"""

import ctypes
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

from src.core import paths as core_paths

SERVICE_NAME = "CollectionAIScheduler"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _service_command() -> List[str]:
    """The [exe] (or [python, script]) to invoke, verb appended by the caller."""
    if core_paths.is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        return [str(exe_dir / "CollectionAI-Service.exe")]
    repo_root = Path(__file__).resolve().parents[2]
    return [sys.executable, str(repo_root / "service_app.py")]


def run_service_action(verb: str) -> Tuple[bool, str]:
    """verb: install | remove | start | stop. Elevates via UAC when needed."""
    base_cmd = _service_command()
    exe, *lead_args = base_cmd
    args = lead_args + [verb]

    if not is_admin():
        params = " ".join(f'"{a}"' for a in args)
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        if int(ret) <= 32:
            return False, "Elevation was cancelled or failed."
        return True, f"'{verb}' launched in an elevated window — check status in a few seconds."

    try:
        result = subprocess.run([exe, *args], capture_output=True, text=True, timeout=30)
        ok = result.returncode == 0
        message = (result.stdout + result.stderr).strip() or ("OK" if ok else "Failed")
        return ok, message
    except Exception as e:
        return False, str(e)


def query_status() -> str:
    """Returns 'RUNNING', 'STOPPED', 'NOT_INSTALLED', or 'UNKNOWN'."""
    try:
        result = subprocess.run(
            ["sc", "query", SERVICE_NAME], capture_output=True, text=True, timeout=10
        )
        out = result.stdout
        if "1060" in out or "does not exist" in out.lower():
            return "NOT_INSTALLED"
        if "RUNNING" in out:
            return "RUNNING"
        if "STOPPED" in out:
            return "STOPPED"
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"
