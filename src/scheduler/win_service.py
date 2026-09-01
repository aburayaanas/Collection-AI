"""
Windows Service wrapper for the Collection AI scheduler.

Manage from an elevated (Administrator) prompt:

    CollectionAI-Service.exe install
    CollectionAI-Service.exe start
    CollectionAI-Service.exe stop
    CollectionAI-Service.exe remove
    CollectionAI-Service.exe debug      # runs in the foreground for troubleshooting

The Configuration app's "Service" tab shells out to these same verbs
(elevated via UAC) rather than re-implementing service management.

Right after a successful ``install``, this also configures the service's
Windows failure-recovery actions (auto-restart, 3 attempts, 1 min apart)
so an unhandled crash in the scheduler process doesn't require someone to
notice and restart it by hand.
"""

import subprocess
import sys

import servicemanager
import win32event
import win32service
import win32serviceutil

from src.core.logger import setup_logging
from src.scheduler.service import SchedulerService


class CollectionAIService(win32serviceutil.ServiceFramework):
    _svc_name_ = "CollectionAIScheduler"
    _svc_display_name_ = "Collection AI - NBA Scheduler"
    _svc_description_ = (
        "Runs the Collection AI Willingness/Ability/NBA batch pipeline on "
        "the schedule configured via the Collection AI Configuration app."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.scheduler_service: SchedulerService | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.scheduler_service:
            self.scheduler_service.stop()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        setup_logging()
        self.scheduler_service = SchedulerService()
        self.scheduler_service.start()
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)


def _configure_auto_restart() -> None:
    """Auto-restart on crash: 3 attempts, 1 minute apart, reset after 1 day."""
    try:
        subprocess.run(
            [
                "sc", "failure", CollectionAIService._svc_name_,
                "reset=", "86400",
                "actions=", "restart/60000/restart/60000/restart/60000",
            ],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        pass  # best-effort; service still works without recovery actions


def main():
    if len(sys.argv) == 1:
        # No CLI args means the Service Control Manager started us.
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(CollectionAIService)
        servicemanager.StartServiceCtrlDispatcher()
        return

    win32serviceutil.HandleCommandLine(CollectionAIService)

    if sys.argv[1].lower() == "install":
        _configure_auto_restart()


if __name__ == "__main__":
    main()
