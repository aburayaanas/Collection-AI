"""
Collection AI - Configuration app.

A CustomTkinter GUI that is the single place an operator touches to:
  - edit every .env value the pipeline reads (Database / Pipeline /
    Narrative API tabs),
  - manage the schedule the Service exe runs against (Schedule tab),
  - install/start/stop the Windows Service (Service tab),
  - tail the latest pipeline log (Logs tab).

Two files are the entire contract with the Service exe: .env and
schedule.json (both under src/core/paths.APP_DIR). Both are written
atomically here, and the running service polls them for changes — see
src/scheduler/service.py — so most edits take effect within ~15s without
restarting the service.
"""

import json
import threading
import time
import tkinter.messagebox as messagebox
from datetime import datetime
from typing import Dict, Optional

import customtkinter as ctk
from apscheduler.triggers.cron import CronTrigger

from src.core import paths
from src.gui_config import env_io, service_control
from src.scheduler.jobstore import VALID_DAYS, VALID_MODEL_SCOPES, VALID_MODES, VALID_SHAP_SCOPES, ScheduledJob, load_jobs, save_jobs
from src.scheduler.runner import get_status

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

WINDOW_SIZE = "1000x700"
LABEL_WIDTH = 220
ENTRY_WIDTH = 380


class ConfigApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Collection AI - Configuration")
        self.geometry(WINDOW_SIZE)
        self.minsize(860, 600)

        self._values: Dict[str, str] = env_io.read_env()
        self._widgets: Dict[str, ctk.CTkBaseClass] = {}
        self._bool_vars: Dict[str, ctk.StringVar] = {}
        self._jobs = load_jobs()

        self._build_layout()
        self._refresh_service_status()
        self._refresh_logs()

    # ── layout ───────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(16, 8))

        for section in env_io.SECTIONS:
            tab = self.tabview.add(section)
            self._build_field_tab(tab, section)

        self._build_schedule_tab(self.tabview.add("Schedule"))
        self._build_service_tab(self.tabview.add("Service"))
        self._build_logs_tab(self.tabview.add("Logs"))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(0, 16))
        self.status_label = ctk.CTkLabel(bottom, text="", anchor="w")
        self.status_label.pack(side="left", padx=(4, 0))
        ctk.CTkButton(bottom, text="Save Configuration", command=self._on_save, width=180).pack(side="right")

    def _build_field_tab(self, tab, section: str) -> None:
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        for field in env_io.FIELD_SCHEMA:
            if field.section != section:
                continue
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=6)

            label = ctk.CTkLabel(row, text=field.label, width=LABEL_WIDTH, anchor="w")
            label.pack(side="left")

            value = self._values.get(field.key, field.default)
            widget = self._make_field_widget(row, field, value)
            self._widgets[field.key] = widget

            if field.help_text:
                is_warning = "TESTING ONLY" in field.help_text or "production" in field.help_text.lower()
                help_label = ctk.CTkLabel(
                    scroll, text=field.help_text, anchor="w",
                    text_color=("#B00020", "#FF6B6B") if is_warning else ("gray40", "gray60"),
                    font=ctk.CTkFont(size=11, weight="bold" if is_warning else "normal"),
                )
                help_label.pack(fill="x", padx=(LABEL_WIDTH + 12, 0))

    def _make_field_widget(self, parent, field: env_io.Field, value: str):
        if field.kind == "bool":
            var = ctk.StringVar(value=value)
            self._bool_vars[field.key] = var
            widget = ctk.CTkSwitch(parent, text="", variable=var, onvalue="True", offvalue="False")
            widget.pack(side="left")
            return widget
        if field.kind == "choice":
            var = ctk.StringVar(value=value or (field.choices[0] if field.choices else ""))
            widget = ctk.CTkOptionMenu(parent, values=field.choices or [], variable=var, width=ENTRY_WIDTH)
            widget.pack(side="left")
            return widget
        if field.kind == "secret":
            container = ctk.CTkFrame(parent, fg_color="transparent")
            container.pack(side="left")
            entry = ctk.CTkEntry(container, width=ENTRY_WIDTH - 70, show="*")
            entry.insert(0, value)
            entry.pack(side="left")
            toggle = ctk.CTkButton(
                container, text="Show", width=60,
                command=lambda e=entry: self._toggle_secret(e),
            )
            toggle.pack(side="left", padx=(6, 0))
            return entry
        # str / int / float
        entry = ctk.CTkEntry(parent, width=ENTRY_WIDTH)
        entry.insert(0, value)
        entry.pack(side="left")
        return entry

    @staticmethod
    def _toggle_secret(entry: ctk.CTkEntry) -> None:
        entry.configure(show="" if entry.cget("show") == "*" else "*")

    def _get_widget_value(self, key: str) -> str:
        if key in self._bool_vars:
            return self._bool_vars[key].get()
        return self._widgets[key].get()

    # ── save / validation ───────────────────────────────────────────

    def _on_save(self) -> None:
        new_values: Dict[str, str] = dict(self._values)
        errors = []

        for field in env_io.FIELD_SCHEMA:
            raw = self._get_widget_value(field.key).strip()
            if field.kind == "int" and raw:
                try:
                    int(raw)
                except ValueError:
                    errors.append(f"{field.label} must be a whole number.")
            elif field.kind == "float" and raw:
                try:
                    float(raw)
                except ValueError:
                    errors.append(f"{field.label} must be a number.")
            new_values[field.key] = raw

        if not new_values.get("DB_USER"):
            errors.append("DB Username is required.")
        if not new_values.get("DB_PASSWORD"):
            errors.append("DB Password is required.")
        if not new_values.get("DB_DSN"):
            errors.append("DB DSN is required.")

        if errors:
            messagebox.showerror("Cannot Save", "Please fix the following:\n\n" + "\n".join(f"- {e}" for e in errors))
            return

        try:
            env_io.write_env(new_values)
            self._values = new_values
            self._set_status("Configuration saved. The running service picks up changes within ~15s.", ok=True)
        except OSError as e:
            messagebox.showerror("Save Failed", f"Could not write configuration file:\n{e}")

    def _set_status(self, text: str, ok: bool = True) -> None:
        self.status_label.configure(text=text, text_color=("#1B7F3A", "#4CD964") if ok else ("#B00020", "#FF6B6B"))

    # ── Schedule tab ─────────────────────────────────────────────────

    def _build_schedule_tab(self, tab) -> None:
        header = ctk.CTkFrame(tab, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(4, 8))
        ctk.CTkLabel(
            header,
            text="Each entry runs the pipeline at a specific time with its own mode/scope "
                 "— e.g. a light SCORE-only refresh morning and evening, plus a nightly FULL retrain.",
            anchor="w", wraplength=880, justify="left",
        ).pack(side="left")
        ctk.CTkButton(header, text="+ Add Job", width=120, command=self._open_job_editor).pack(side="right")

        self.jobs_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.jobs_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self._render_jobs()

    def _render_jobs(self) -> None:
        for child in self.jobs_frame.winfo_children():
            child.destroy()

        if not self._jobs:
            ctk.CTkLabel(self.jobs_frame, text="No scheduled jobs yet. Click '+ Add Job' to create one.").pack(pady=20)
            return

        for job in sorted(self._jobs, key=lambda j: (j.hour, j.minute)):
            card = ctk.CTkFrame(self.jobs_frame, corner_radius=10)
            card.pack(fill="x", pady=6, padx=2)

            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True, padx=12, pady=10)

            title = f"{job.name}   •   {job.time_label()} (24h)   •   {job.days_label()}"
            ctk.CTkLabel(left, text=title, font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            subtitle = f"Mode: {job.mode}   |   Model Scope: {job.model_scope}   |   SHAP: {job.shap_scope}"
            ctk.CTkLabel(left, text=subtitle, text_color=("gray40", "gray60")).pack(anchor="w")
            next_run_text = self._next_run_label(job)
            ctk.CTkLabel(left, text=next_run_text, text_color=("#1B7F3A", "#4CD964") if job.enabled else ("gray40", "gray60")).pack(anchor="w")

            right = ctk.CTkFrame(card, fg_color="transparent")
            right.pack(side="right", padx=12, pady=10)

            enabled_var = ctk.StringVar(value="on" if job.enabled else "off")
            ctk.CTkSwitch(
                right, text="Enabled", variable=enabled_var, onvalue="on", offvalue="off",
                command=lambda j=job, v=enabled_var: self._toggle_job(j, v.get() == "on"),
            ).pack(side="left", padx=6)
            ctk.CTkButton(right, text="Run Now", width=90, command=lambda j=job: self._run_now(j)).pack(side="left", padx=6)
            ctk.CTkButton(right, text="Edit", width=70, command=lambda j=job: self._open_job_editor(j)).pack(side="left", padx=6)
            ctk.CTkButton(
                right, text="Delete", width=70, fg_color="#B00020", hover_color="#8C0019",
                command=lambda j=job: self._delete_job(j),
            ).pack(side="left", padx=6)

    @staticmethod
    def _next_run_label(job: ScheduledJob) -> str:
        """
        Computed with the exact same CronTrigger the running Service uses
        (src/scheduler/service.py), so what this shows always matches what
        will actually happen — including the easy-to-miss case of an
        hour/minute that's already passed today rolling to tomorrow.
        """
        if not job.enabled:
            return "Disabled"
        trigger = CronTrigger(hour=job.hour, minute=job.minute, day_of_week=job.cron_day_of_week())
        next_run = trigger.get_next_fire_time(None, datetime.now(trigger.timezone))
        if next_run is None:
            return "Next run: never (check days selected)"
        return f"Next run: {next_run.strftime('%a %Y-%m-%d %H:%M')}"

    def _persist_jobs(self, message: str = "Schedule saved.") -> None:
        save_jobs(self._jobs)
        self._render_jobs()
        self._set_status(message, ok=True)

    def _toggle_job(self, job: ScheduledJob, enabled: bool) -> None:
        job.enabled = enabled
        self._persist_jobs()

    def _delete_job(self, job: ScheduledJob) -> None:
        if not messagebox.askyesno("Delete Job", f"Delete scheduled job '{job.name}'?"):
            return
        self._jobs = [j for j in self._jobs if j.id != job.id]
        self._persist_jobs("Job deleted.")

    def _run_now(self, job: ScheduledJob) -> None:
        payload = {"name": job.name, "mode": job.mode, "model_scope": job.model_scope, "shap_scope": job.shap_scope}
        tmp_path = paths.RUN_NOW_FLAG_PATH.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload), encoding="utf-8")
        tmp_path.replace(paths.RUN_NOW_FLAG_PATH)
        self._set_status(f"Queued '{job.name}' — picked up within ~15s if the service is running.", ok=True)

    def _open_job_editor(self, job: Optional[ScheduledJob] = None) -> None:
        JobEditorDialog(self, job, on_save=self._on_job_saved)

    def _on_job_saved(self, job: ScheduledJob, is_new: bool) -> None:
        if is_new:
            self._jobs.append(job)
        else:
            self._jobs = [job if j.id == job.id else j for j in self._jobs]
        self._persist_jobs()

    # ── Service tab ──────────────────────────────────────────────────

    def _build_service_tab(self, tab) -> None:
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        self.service_status_label = ctk.CTkLabel(frame, text="Status: checking...", font=ctk.CTkFont(size=16, weight="bold"))
        self.service_status_label.pack(anchor="w", pady=(0, 16))

        if not service_control.is_admin():
            ctk.CTkLabel(
                frame,
                text="Install/Start/Stop require Administrator rights — you'll see a UAC prompt.",
                text_color=("gray40", "gray60"),
            ).pack(anchor="w", pady=(0, 10))

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(anchor="w")
        for label, verb in [("Install", "install"), ("Start", "start"), ("Stop", "stop"), ("Remove", "remove")]:
            ctk.CTkButton(btn_row, text=label, width=100, command=lambda v=verb: self._service_action(v)).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Refresh", width=100, command=self._refresh_service_status).pack(side="left", padx=6)

        ctk.CTkLabel(frame, text="Last Pipeline Run", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(24, 6))
        self.last_run_label = ctk.CTkLabel(frame, text="—", justify="left", anchor="w")
        self.last_run_label.pack(anchor="w")

    def _service_action(self, verb: str) -> None:
        def worker():
            ok, message = service_control.run_service_action(verb)
            self.after(0, lambda: self._set_status(message, ok=ok))
            self.after(1500, self._refresh_service_status)
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_service_status(self) -> None:
        def worker():
            status = service_control.query_status()
            self.after(0, lambda: self._apply_service_status(status))
        threading.Thread(target=worker, daemon=True).start()
        self._refresh_last_run()

    def _apply_service_status(self, status: str) -> None:
        colors = {
            "RUNNING": ("#1B7F3A", "#4CD964"),
            "STOPPED": ("#B00020", "#FF6B6B"),
            "NOT_INSTALLED": ("gray40", "gray60"),
            "UNKNOWN": ("gray40", "gray60"),
        }
        self.service_status_label.configure(text=f"Status: {status.replace('_', ' ').title()}", text_color=colors.get(status, "gray"))

    def _refresh_last_run(self) -> None:
        status = get_status()
        last = status.get("last")
        current = status.get("current")
        if current:
            text = f"RUNNING NOW — '{current['job_name']}' (started {current['started_at']})"
        elif last:
            text = (
                f"{last['job_name']}  |  {last['status']}  |  "
                f"started {last['started_at']}  |  ended {last.get('ended_at', '—')}"
            )
            if last.get("error"):
                text += f"\n{last['error']}"
        else:
            text = "No runs recorded yet."
        self.last_run_label.configure(text=text)

    # ── Logs tab ─────────────────────────────────────────────────────

    def _build_logs_tab(self, tab) -> None:
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text="Latest pipeline log (last 300 lines)").pack(side="left")
        ctk.CTkButton(header, text="Refresh", width=100, command=self._refresh_logs).pack(side="right")

        self.log_box = ctk.CTkTextbox(frame, wrap="none", font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.pack(fill="both", expand=True, pady=(8, 0))
        self.log_box.configure(state="disabled")

    def _refresh_logs(self) -> None:
        log_files = sorted(paths.LOGS_DIR.glob("collection_batch_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        content = "(No log files yet — run the pipeline at least once.)"
        if log_files:
            try:
                text = log_files[0].read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()[-300:]
                content = "\n".join(lines)
            except OSError as e:
                content = f"(Could not read log file: {e})"

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("1.0", content)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


class JobEditorDialog(ctk.CTkToplevel):
    def __init__(self, parent: ConfigApp, job: Optional[ScheduledJob], on_save):
        super().__init__(parent)
        self.title("Edit Job" if job else "Add Job")
        self.geometry("420x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._original = job
        self._on_save = on_save

        pad = {"padx": 16, "pady": 6}

        self.name_entry = self._labeled_entry("Job Name", job.name if job else "Morning Refresh", **pad)
        time_row = ctk.CTkFrame(self, fg_color="transparent")
        time_row.pack(fill="x", **pad)
        ctk.CTkLabel(time_row, text="Time (HH:MM)", width=LABEL_WIDTH, anchor="w").pack(side="left")
        self.hour_entry = ctk.CTkEntry(time_row, width=50)
        self.hour_entry.insert(0, f"{job.hour:02d}" if job else "07")
        self.hour_entry.pack(side="left")
        ctk.CTkLabel(time_row, text=":").pack(side="left", padx=4)
        self.minute_entry = ctk.CTkEntry(time_row, width=50)
        self.minute_entry.insert(0, f"{job.minute:02d}" if job else "00")
        self.minute_entry.pack(side="left")
        ctk.CTkLabel(
            self, text="24-hour clock — e.g. 3:58 PM is 15:58, not 3:58. Check \"Next run\" after saving.",
            text_color=("gray40", "gray60"), font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=16)

        ctk.CTkLabel(self, text="Days", anchor="w").pack(fill="x", padx=16, pady=(12, 2))
        days_row = ctk.CTkFrame(self, fg_color="transparent")
        days_row.pack(fill="x", padx=16)
        selected_days = set(job.days if job else VALID_DAYS)
        self.day_vars: Dict[str, ctk.BooleanVar] = {}
        for day in VALID_DAYS:
            var = ctk.BooleanVar(value=day in selected_days)
            self.day_vars[day] = var
            ctk.CTkCheckBox(days_row, text=day.capitalize(), variable=var, width=20).pack(side="left", padx=4)

        self.mode_menu = self._labeled_option("Mode", list(VALID_MODES), job.mode if job else "SCORE", **pad)
        self.model_scope_menu = self._labeled_option("Model Scope", list(VALID_MODEL_SCOPES), job.model_scope if job else "BOTH", **pad)
        self.shap_scope_menu = self._labeled_option("SHAP Scope", list(VALID_SHAP_SCOPES), job.shap_scope if job else "BOTH", **pad)

        self.error_label = ctk.CTkLabel(self, text="", text_color=("#B00020", "#FF6B6B"), wraplength=380)
        self.error_label.pack(fill="x", padx=16, pady=(8, 0))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=16, side="bottom")
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray40", command=self.destroy).pack(side="right", padx=(6, 0))
        ctk.CTkButton(btn_row, text="Save", command=self._save).pack(side="right")

    def _labeled_entry(self, label: str, value: str, **pad) -> ctk.CTkEntry:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", **pad)
        ctk.CTkLabel(row, text=label, width=LABEL_WIDTH, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, width=180)
        entry.insert(0, value)
        entry.pack(side="left")
        return entry

    def _labeled_option(self, label: str, choices, value: str, **pad) -> ctk.CTkOptionMenu:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", **pad)
        ctk.CTkLabel(row, text=label, width=LABEL_WIDTH, anchor="w").pack(side="left")
        var = ctk.StringVar(value=value)
        menu = ctk.CTkOptionMenu(row, values=choices, variable=var, width=180)
        menu.pack(side="left")
        return menu

    def _save(self) -> None:
        try:
            hour = int(self.hour_entry.get())
            minute = int(self.minute_entry.get())
            days = [d for d, v in self.day_vars.items() if v.get()]
            kwargs = dict(
                name=self.name_entry.get().strip() or "Untitled Job",
                enabled=self._original.enabled if self._original else True,
                hour=hour,
                minute=minute,
                days=days,
                mode=self.mode_menu.get(),
                model_scope=self.model_scope_menu.get(),
                shap_scope=self.shap_scope_menu.get(),
            )
            if self._original:
                kwargs["id"] = self._original.id
            job = ScheduledJob(**kwargs)
        except Exception as e:
            self.error_label.configure(text=str(e))
            return

        self._on_save(job, is_new=self._original is None)
        self.destroy()


def run() -> None:
    app = ConfigApp()
    app.mainloop()


if __name__ == "__main__":
    run()
