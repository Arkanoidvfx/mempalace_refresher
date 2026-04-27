from __future__ import annotations

from pathlib import Path
from threading import Event, Lock, Thread
import json
import os
import shutil
import subprocess
import time
import re
import webbrowser

from .config import AppConfig, load_config, save_config
from .core import ProjectRecord, ScanResult, iso_now
from .db import Database
from .discovery import discover_projects
from .scanner import collect_change_snapshot, scan_project
from .windows import hidden_subprocess_kwargs


REFRESH_PROGRESS_RULES: tuple[tuple[re.Pattern[str], int, str], ...] = (
    (re.compile(r"^Staged \d+ file\(s\) into "), 15, "Staging files"),
    (re.compile(r"^Missing manifest path\(s\): "), 20, "Checking manifest"),
    (re.compile(r"^StageOnly set; skipping MemPalace install and mining\."), 25, "Stage only"),
    (re.compile(r"^Creating project-local virtual environment: "), 40, "Creating virtual environment"),
    (re.compile(r"^Installing .* into project-local virtual environment\.\.\.$"), 70, "Installing MemPalace"),
    (re.compile(r"^Rebuilding palace from curated staging corpus: "), 90, "Rebuilding palace"),
    (re.compile(r"^Updated MemPalace drawer importance metadata: "), 96, "Updating importance metadata"),
)

PROJECT_LOG_EVENT_LIMIT = 25


class WatcherService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.state_dir = self.project_root / "state"
        self.config_path = self.state_dir / "config.json"
        self.legacy_config_path = self.project_root / "config.json"
        self.db = Database(self.state_dir / "mempalace_watcher.sqlite3")
        self.config = load_config(self.config_path, legacy_path=self.legacy_config_path)
        self._refresh_lock = Lock()
        self._refresh_states: dict[str, dict[str, object]] = {}
        self._project_scan_lock = Lock()
        self._project_scan_states: dict[str, dict[str, object]] = {}
        self._scan_lock = Lock()
        self._scan_state: dict[str, object] = self._default_scan_state()

    def reload_config(self) -> AppConfig:
        self.config = load_config(self.config_path, legacy_path=self.legacy_config_path)
        return self.config

    def save_config(self, config: AppConfig) -> None:
        self.config = config
        save_config(self.config_path, config)

    def discover(self) -> list[ProjectRecord]:
        config = self.reload_config()
        projects = discover_projects(config)
        self_root = self.project_root.resolve()
        tracked_paths: list[str] = []
        for project in projects:
            if project.path.resolve() == self_root:
                continue
            tracked_paths.append(str(project.path))
            self.db.upsert_project(
                path=str(project.path),
                name=project.name,
                marker_path=str(project.marker_path),
                refresh_script=str(project.refresh_script),
                last_seen=iso_now(),
            )
        self.db.prune_projects(tracked_paths)
        return projects

    def _get_project_row(self, path: str):
        return self.db.get_project(path)

    def _accepted_change_snapshot(self, row) -> list[dict[str, object]] | None:
        payload = row["accepted_change_snapshot_json"]
        if not payload:
            return None
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list):
            return None
        accepted: list[dict[str, object]] = []
        for item in data:
            if isinstance(item, dict):
                accepted.append(item)
        return accepted or None

    def scan(self) -> list[ScanResult]:
        return self._scan_projects(track_state=False)

    def _default_scan_state(self) -> dict[str, object]:
        return {
            "active": False,
            "done": False,
            "phase": "Idle",
            "message": "Ready to scan",
            "percent": 0,
            "total": 0,
            "completed": 0,
            "current_path": "",
            "current_name": "",
            "started_at": None,
            "updated_at": None,
            "finished_at": None,
            "error": None,
        }

    def _set_scan_state(self, **updates: object) -> dict[str, object]:
        with self._scan_lock:
            state = dict(self._scan_state)
            state.update(updates)
            state["updated_at"] = iso_now()
            self._scan_state = state
            return dict(state)

    def scan_state(self) -> dict[str, object]:
        with self._scan_lock:
            return dict(self._scan_state)

    def _scan_projects(self, *, track_state: bool) -> list[ScanResult]:
        if track_state:
            self._set_scan_state(
                active=True,
                done=False,
                phase="Discovering",
                message="Discovering tracked projects",
                percent=1,
                total=0,
                completed=0,
                current_path="",
                current_name="",
                started_at=iso_now(),
                finished_at=None,
                error=None,
            )
        self.discover()
        config = self.config
        rows = list(self.db.list_projects())
        results: list[ScanResult] = []
        total = len(rows)
        if track_state:
            self._set_scan_state(
                total=total,
                phase="Scanning",
                message=f"Scanning {total} project(s)",
                percent=3 if total else 100,
            )
        for index, row in enumerate(rows, start=1):
            if track_state:
                self._set_scan_state(
                    current_path=str(row["path"]),
                    current_name=str(row["name"]),
                    completed=index - 1,
                    total=total,
                    percent=min(95, max(3, int(((index - 1) / max(total, 1)) * 100))),
                    phase="Scanning",
                    message=f"Scanning {row['name']} ({index}/{max(total, 1)})",
                )
            result, _ = self._scan_row(row, config)
            results.append(result)
            if track_state:
                self._set_scan_state(
                    current_path=str(row["path"]),
                    current_name=str(row["name"]),
                    completed=index,
                    total=total,
                    percent=min(99, max(5, int((index / max(total, 1)) * 100))),
                    phase="Scanning",
                    message=f"{row['name']} -> {result.status}",
                )
        if track_state:
            self._set_scan_state(
                active=False,
                done=True,
                phase="Complete",
                message=f"Scanned {total} project(s)",
                percent=100,
                completed=total,
                total=total,
                current_path="",
                current_name="",
                finished_at=iso_now(),
                error=None,
            )
        return results

    def _scan_row(self, row, config: AppConfig) -> tuple[ScanResult, list[str]]:
        result, samples = scan_project(
            root=Path(row["path"]),
            name=row["name"],
            last_refresh=row["last_refresh"],
            last_status=row["last_status"],
            last_error=row["last_error"],
            paused=bool(row["paused"]),
            config=config,
            accepted_change_snapshot=self._accepted_change_snapshot(row),
        )
        self.db.update_scan_state(
            path=row["path"],
            last_seen=result.last_seen or iso_now(),
            last_refresh=row["last_refresh"],
            last_status=result.status,
            last_error=result.error,
            drift_score=result.drift_score,
            change_count=result.change_count,
            critical_change_count=result.critical_change_count,
            age_hours=result.age_hours,
            last_reason="; ".join(result.reasons),
        )
        self.db.log_event(
            path=row["path"],
            kind="scan",
            status=result.status,
            message="; ".join(result.reasons),
        )
        return result, samples

    def _default_refresh_state(self, path: str) -> dict[str, object]:
        return {
            "path": path,
            "active": False,
            "percent": 0,
            "phase": "",
            "message": "",
            "started_at": None,
            "updated_at": None,
            "done": False,
            "error": None,
        }

    def _set_refresh_state(self, path: str, **updates: object) -> dict[str, object]:
        with self._refresh_lock:
            state = dict(self._refresh_states.get(path) or self._default_refresh_state(path))
            state.update(updates)
            state["path"] = path
            state["updated_at"] = iso_now()
            self._refresh_states[path] = state
            return dict(state)

    def refresh_state(self, path: str) -> dict[str, object]:
        with self._refresh_lock:
            return dict(self._refresh_states.get(path) or self._default_refresh_state(path))

    def all_refresh_states(self) -> dict[str, dict[str, object]]:
        with self._refresh_lock:
            return {path: dict(state) for path, state in self._refresh_states.items()}

    def active_refresh_count(self) -> int:
        with self._refresh_lock:
            return sum(1 for state in self._refresh_states.values() if state.get("active"))

    def _default_project_scan_state(self, path: str) -> dict[str, object]:
        return {
            "path": path,
            "active": False,
            "percent": 0,
            "phase": "",
            "message": "",
            "started_at": None,
            "updated_at": None,
            "done": False,
            "error": None,
        }

    def _set_project_scan_state(self, path: str, **updates: object) -> dict[str, object]:
        with self._project_scan_lock:
            state = dict(self._project_scan_states.get(path) or self._default_project_scan_state(path))
            state.update(updates)
            state["path"] = path
            state["updated_at"] = iso_now()
            self._project_scan_states[path] = state
            return dict(state)

    def project_scan_state(self, path: str) -> dict[str, object]:
        with self._project_scan_lock:
            return dict(self._project_scan_states.get(path) or self._default_project_scan_state(path))

    def all_project_scan_states(self) -> dict[str, dict[str, object]]:
        with self._project_scan_lock:
            return {path: dict(state) for path, state in self._project_scan_states.items()}

    def active_project_scan_count(self) -> int:
        with self._project_scan_lock:
            return sum(1 for state in self._project_scan_states.values() if state.get("active"))

    def _infer_refresh_progress(self, line: str, current_percent: int) -> tuple[int, str]:
        for pattern, percent, phase in REFRESH_PROGRESS_RULES:
            if pattern.search(line):
                return max(current_percent, percent), phase
        return current_percent, ""

    def _resolve_powershell(self) -> str:
        candidates = ("pwsh.exe", "pwsh", "powershell.exe", "powershell")
        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        raise FileNotFoundError("No PowerShell executable found in PATH (pwsh.exe or powershell.exe)")

    def refresh_project(self, path: str, dry_run: bool = False) -> ScanResult:
        row = self._get_project_row(path)
        if row is None:
            raise FileNotFoundError(f"Project not found: {path}")
        config = self.config
        project_path = Path(row["path"])
        if bool(row["paused"]):
            result, _ = scan_project(
                root=project_path,
                name=row["name"],
                last_refresh=row["last_refresh"],
                last_status=row["last_status"],
                last_error=row["last_error"],
                paused=True,
                config=config,
                accepted_change_snapshot=self._accepted_change_snapshot(row),
            )
            return result

        script_rel = Path("scripts") / "mempalace_refresh.ps1"
        script = project_path / script_rel
        if not script.is_file():
            failure_reason = f"Refresh script missing: {script}"
            failed_result, _ = scan_project(
                root=project_path,
                name=row["name"],
                last_refresh=row["last_refresh"],
                last_status="error",
                last_error=failure_reason,
                paused=False,
                config=config,
                accepted_change_snapshot=self._accepted_change_snapshot(row),
            )
            self.db.update_scan_state(
                path=path,
                last_seen=iso_now(),
                last_refresh=row["last_refresh"],
                last_status=failed_result.status,
                last_error=failure_reason,
                drift_score=failed_result.drift_score,
                change_count=failed_result.change_count,
                critical_change_count=failed_result.critical_change_count,
                age_hours=failed_result.age_hours,
                last_reason="; ".join(failed_result.reasons),
            )
            self.db.log_event(
                path=path,
                kind="refresh",
                status="error",
                message=failure_reason[:3000],
            )
            return failed_result

        if dry_run:
            self.db.log_event(
                path=path,
                kind="refresh",
                status="dry_run",
                message="refresh skipped by dry-run",
            )
            result, _ = scan_project(
                root=project_path,
                name=row["name"],
                last_refresh=row["last_refresh"],
                last_status=row["last_status"],
                last_error=row["last_error"],
                paused=False,
                config=config,
                accepted_change_snapshot=self._accepted_change_snapshot(row),
            )
            return result

        start = time.perf_counter()
        refresh_started_at = iso_now()
        powershell_exe = self._resolve_powershell()
        self._set_refresh_state(
            path,
            active=True,
            done=False,
            percent=1,
            phase="Launching refresh",
            message=f"Running {script_rel}",
            started_at=refresh_started_at,
            error=None,
        )
        proc = subprocess.Popen(
            [
                powershell_exe,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_rel),
            ],
            cwd=str(project_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **hidden_subprocess_kwargs(),
        )
        output_parts: list[str] = []
        current_percent = 1
        current_phase = "Launching refresh"

        def consume_output() -> None:
            nonlocal current_percent, current_phase
            if proc.stdout is None:
                return
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\r\n")
                if not line:
                    continue
                output_parts.append(line)
                current_percent, phase = self._infer_refresh_progress(line, current_percent)
                if phase:
                    current_phase = phase
                elif not current_phase:
                    current_phase = "Running refresh"
                self._set_refresh_state(
                    path,
                    active=True,
                    done=False,
                    percent=min(max(current_percent, 1), 99),
                    phase=current_phase,
                    message=line,
                    started_at=refresh_started_at,
                    error=None,
                )

        reader = Thread(target=consume_output, daemon=True)
        reader.start()
        timed_out = False
        try:
            proc.wait(timeout=config.refresh_timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
        finally:
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            reader.join(timeout=5)

        duration_ms = int((time.perf_counter() - start) * 1000)
        combined_output = "\n".join(output_parts).strip()

        if timed_out:
            failure_reason = combined_output or f"Refresh timed out after {config.refresh_timeout_seconds} seconds"
            self._set_refresh_state(
                path,
                active=False,
                done=True,
                percent=current_percent,
                phase="Timed out",
                message=failure_reason,
                error=failure_reason,
            )
            failed_result, _ = scan_project(
                root=project_path,
                name=row["name"],
                last_refresh=row["last_refresh"],
                last_status="error",
                last_error=failure_reason,
                paused=False,
                config=config,
                accepted_change_snapshot=self._accepted_change_snapshot(row),
            )
            self.db.update_scan_state(
                path=path,
                last_seen=iso_now(),
                last_refresh=row["last_refresh"],
                last_status=failed_result.status,
                last_error=failure_reason,
                drift_score=failed_result.drift_score,
                change_count=failed_result.change_count,
                critical_change_count=failed_result.critical_change_count,
                age_hours=failed_result.age_hours,
                last_reason="; ".join(failed_result.reasons),
            )
            self.db.log_event(
                path=path,
                kind="refresh",
                status="error",
                message=(failure_reason)[:3000],
                duration_ms=duration_ms,
            )
            return failed_result

        if proc.returncode == 0:
            refresh_completed_at = iso_now()
            prev_count = int(row["refresh_count"] or 0)
            prev_avg = row["refresh_avg_duration_ms"]
            new_count = prev_count + 1
            new_avg = duration_ms if prev_avg is None or prev_count <= 0 else int(
                round(((int(prev_avg) * prev_count) + duration_ms) / new_count)
            )
            accepted_snapshot = collect_change_snapshot(project_path, row["last_refresh"], config).to_records()
            fresh_result, _ = scan_project(
                root=project_path,
                name=row["name"],
                last_refresh=refresh_completed_at,
                last_status="fresh",
                last_error=None,
                paused=False,
                config=config,
                accepted_change_snapshot=accepted_snapshot,
            )
            fresh_result.status = "fresh"
            fresh_result.drift_score = 0
            fresh_result.change_count = 0
            fresh_result.critical_change_count = 0
            fresh_result.age_hours = 0.0
            fresh_result.error = None
            fresh_result.reasons = ["refresh completed successfully"]
            fresh_result.changed_samples = []
            self._set_refresh_state(
                path,
                active=False,
                done=True,
                percent=100,
                phase="Complete",
                message="refresh completed successfully",
                error=None,
            )
            self.db.update_refresh_state(
                path=path,
                last_refresh=refresh_completed_at,
                last_status="fresh",
                last_error=None,
                drift_score=0,
                change_count=0,
                critical_change_count=0,
                age_hours=0.0,
                last_reason="refresh completed successfully",
                refresh_count=new_count,
                last_refresh_duration_ms=duration_ms,
                refresh_avg_duration_ms=new_avg,
                accepted_change_snapshot_json=json.dumps(accepted_snapshot, ensure_ascii=False),
                accepted_change_snapshot_at=refresh_completed_at,
            )
            self.db.log_event(
                path=path,
                kind="refresh",
                status="success",
                message=(combined_output[:3000] or "refresh completed successfully"),
                duration_ms=duration_ms,
            )
            return fresh_result

        failure_reason = combined_output or f"Refresh failed with exit code {proc.returncode}"
        self._set_refresh_state(
            path,
            active=False,
            done=True,
            percent=current_percent,
            phase="Failed",
            message=failure_reason,
            error=failure_reason,
        )
        failed_result, _ = scan_project(
            root=project_path,
            name=row["name"],
            last_refresh=row["last_refresh"],
            last_status="error",
            last_error=failure_reason,
            paused=False,
            config=config,
            accepted_change_snapshot=self._accepted_change_snapshot(row),
        )
        self.db.update_scan_state(
            path=path,
            last_seen=iso_now(),
            last_refresh=row["last_refresh"],
            last_status=failed_result.status,
            last_error=failure_reason,
            drift_score=failed_result.drift_score,
            change_count=failed_result.change_count,
            critical_change_count=failed_result.critical_change_count,
            age_hours=failed_result.age_hours,
            last_reason="; ".join(failed_result.reasons),
        )
        self.db.log_event(
            path=path,
            kind="refresh",
            status="error",
            message=(failure_reason)[:3000],
            duration_ms=duration_ms,
        )
        return failed_result

    def start_refresh_project(self, path: str, dry_run: bool = False) -> dict[str, object]:
        state = self.refresh_state(path)
        if state.get("active"):
            return state

        def worker() -> None:
            try:
                self.refresh_project(path, dry_run=dry_run)
            except Exception as exc:  # pragma: no cover - defensive
                self._set_refresh_state(
                    path,
                    active=False,
                    done=True,
                    phase="Failed",
                    error=str(exc),
                    message=str(exc),
                )
                self.db.log_event(
                    path=path,
                    kind="refresh",
                    status="error",
                    message=str(exc)[:3000],
                )

        self._set_refresh_state(
            path,
            active=True,
            done=False,
            percent=1,
            phase="Running",
            message="refresh started",
            error=None,
        )
        Thread(target=worker, daemon=True).start()
        return self.refresh_state(path)

    def start_refresh_all_projects(self, dry_run: bool = False) -> dict[str, object]:
        started: list[str] = []
        for row in self.db.list_projects():
            if row["paused"]:
                continue
            path = str(row["path"])
            if self.refresh_state(path).get("active"):
                continue
            if not Path(row["refresh_script"]).is_file():
                continue
            self.start_refresh_project(path, dry_run=dry_run)
            started.append(path)
        return {"ok": True, "started": started}

    def start_refresh_stale(self) -> dict[str, object]:
        started: list[str] = []
        for row in self.db.list_projects():
            if row["paused"]:
                continue
            path = str(row["path"])
            if self.refresh_state(path).get("active"):
                continue
            if not Path(row["refresh_script"]).is_file():
                continue
            if (row["last_status"] or "") not in {"stale", "needs refresh", "error"}:
                continue
            self.start_refresh_project(path)
            started.append(path)
        return {"ok": True, "started": started}

    def refresh_all_projects(self, dry_run: bool = False) -> list[ScanResult]:
        self.discover()
        refreshed: list[ScanResult] = []
        for row in self.db.list_projects():
            if row["paused"]:
                continue
            if self.refresh_state(str(row["path"])).get("active"):
                continue
            if not Path(row["refresh_script"]).is_file():
                continue
            refreshed.append(self.refresh_project(row["path"], dry_run=dry_run))
        return refreshed

    def refresh_stale(self) -> list[ScanResult]:
        refreshed: list[ScanResult] = []
        for row in self.db.list_projects():
            if row["paused"]:
                continue
            if self.refresh_state(str(row["path"])).get("active"):
                continue
            if not Path(row["refresh_script"]).is_file():
                continue
            if (row["last_status"] or "") not in {"stale", "needs refresh", "error"}:
                continue
            refreshed.append(self.refresh_project(row["path"]))
        return refreshed

    def rescan_all(self, apply_refresh: bool = False) -> list[ScanResult]:
        results = self._scan_projects(track_state=False)
        if apply_refresh:
            for result in results:
                row = self.db.get_project(str(result.path))
                if row is None:
                    continue
                if self.refresh_state(str(result.path)).get("active"):
                    continue
                if not Path(row["refresh_script"]).is_file():
                    continue
                if result.status in {"stale", "needs refresh"} and not result.paused:
                    self.start_refresh_project(str(result.path))
        return results

    def start_scan(self) -> dict[str, object]:
        with self._scan_lock:
            if self._scan_state.get("active"):
                return dict(self._scan_state)
            self._scan_state = self._default_scan_state()
            self._scan_state.update(
                {
                    "active": True,
                    "done": False,
                    "phase": "Discovering",
                    "message": "Starting scan",
                    "percent": 1,
                    "started_at": iso_now(),
                    "updated_at": iso_now(),
                }
            )

        def worker() -> None:
            try:
                self._scan_projects(track_state=True)
            except Exception as exc:  # pragma: no cover - defensive
                self._set_scan_state(
                    active=False,
                    done=True,
                    phase="Failed",
                    message=str(exc),
                    error=str(exc),
                    finished_at=iso_now(),
                )
                self.db.log_event(
                    path=str(self.project_root),
                    kind="scan",
                    status="error",
                    message=str(exc)[:3000],
                )

        Thread(target=worker, daemon=True).start()
        return self.scan_state()

    def start_scan_project(self, path: str) -> dict[str, object]:
        row = self._get_project_row(path)
        if row is None:
            raise FileNotFoundError(f"Project not found: {path}")
        state = self.project_scan_state(path)
        if state.get("active"):
            return state

        self._set_project_scan_state(
            path,
            active=True,
            done=False,
            percent=1,
            phase="Starting scan",
            message="Preparing project scan",
            error=None,
            started_at=iso_now(),
        )

        def worker() -> None:
            try:
                self._set_project_scan_state(
                    path,
                    active=True,
                    done=False,
                    percent=15,
                    phase="Reading state",
                    message="Reading current project state",
                    error=None,
                )
                current_row = self._get_project_row(path)
                if current_row is None:
                    raise FileNotFoundError(f"Project not found: {path}")
                self._set_project_scan_state(
                    path,
                    active=True,
                    done=False,
                    percent=45,
                    phase="Scanning",
                    message="Comparing files and scoring drift",
                    error=None,
                )
                result, _ = self._scan_row(current_row, self.config)
                self._set_project_scan_state(
                    path,
                    active=True,
                    done=False,
                    percent=85,
                    phase="Saving results",
                    message=f"Saving scan results: {result.status}",
                    error=None,
                )
                self._set_project_scan_state(
                    path,
                    active=False,
                    done=True,
                    percent=100,
                    phase="Complete",
                    message=f"Scan complete: {result.status}",
                    error=None,
                )
            except Exception as exc:  # pragma: no cover - defensive
                self._set_project_scan_state(
                    path,
                    active=False,
                    done=True,
                    percent=100,
                    phase="Failed",
                    message=str(exc),
                    error=str(exc),
                )
                self.db.log_event(
                    path=path,
                    kind="scan",
                    status="error",
                    message=str(exc)[:3000],
                )

        Thread(target=worker, daemon=True).start()
        return self.project_scan_state(path)

    def summary(self) -> dict[str, int]:
        return self.db.summary()

    def _project_log_lines(self, detail: dict[str, object], events: list[dict[str, object]]) -> list[str]:
        pending_count = int(detail.get("change_count") or 0)
        critical_count = int(detail.get("critical_change_count") or 0)
        lines = [
            f"Project: {detail.get('name') or 'n/a'}",
            f"Path: {detail.get('path') or 'n/a'}",
            f"Status: {detail.get('last_status') or detail.get('status') or 'fresh'}",
            f"Drift: {int(detail.get('drift_score') or 0)}",
            f"Pending: {pending_count} changed files / {critical_count} critical changes",
            f"Age: {detail.get('age_hours') or 0}h",
            f"Last refresh: {detail.get('last_refresh') or 'n/a'}",
            f"Last run: {detail.get('last_refresh_duration_ms') or 'n/a'} ms",
            f"Predicted: {detail.get('refresh_avg_duration_ms') or 'n/a'} ms",
            f"Refresh runs: {int(detail.get('refresh_count') or 0)}",
        ]
        reasons = [str(item).strip() for item in (detail.get("reasons") or []) if str(item).strip()]
        if reasons:
            lines.append(f"Reasons: {'; '.join(reasons)}")
        last_error = detail.get("last_error")
        if last_error:
            lines.append(f"Last error: {last_error}")
        lines.append("")
        lines.append("Recent events (newest first):")
        if not events:
            lines.append("No recent events recorded.")
            return lines
        for event in events:
            line = f"{event['created_at']} [{event['kind']}] {event['status']}"
            duration_ms = event.get("duration_ms")
            if duration_ms is not None:
                line += f" ({duration_ms}ms)"
            message = str(event.get("message") or "").strip()
            if message:
                line += f" - {message}"
            lines.append(line)
        return lines

    def project_detail(self, path: str) -> dict[str, object]:
        row = self.db.get_project(path)
        if row is None:
            raise FileNotFoundError(path)
        events = [
            {
                "kind": item["kind"],
                "status": item["status"],
                "message": item["message"],
                "duration_ms": item["duration_ms"],
                "created_at": item["created_at"],
            }
            for item in self.db.recent_events(path, limit=PROJECT_LOG_EVENT_LIMIT)
        ]
        detail = dict(row)
        detail["events"] = events
        detail["reasons"] = [item.strip() for item in (detail.get("last_reason") or "").split("; ") if item.strip()]
        detail["log_lines"] = self._project_log_lines(detail, events)
        detail["log_text"] = "\n".join(detail["log_lines"])
        return detail

    def set_paused(self, path: str, paused: bool) -> None:
        self.db.set_paused(path, paused)

    def update_config(self, payload: dict[str, object]) -> AppConfig:
        config = AppConfig.from_mapping(payload)
        self.save_config(config)
        return config

    def run_loop(self, stop_event: Event | None = None) -> None:
        stop_event = stop_event or Event()
        while not stop_event.is_set():
            try:
                self.rescan_all(apply_refresh=self.config.auto_refresh)
            except Exception as exc:  # pragma: no cover - defensive
                self.db.log_event(
                    path=str(self.project_root),
                    kind="watch",
                    status="error",
                    message=str(exc),
                )
            stop_event.wait(self.config.watch_interval_seconds)

    def serve_dashboard(self, *, open_browser: bool = True) -> None:
        from .web import build_server

        stop_event = Event()
        thread = Thread(target=self.run_loop, args=(stop_event,), daemon=True)
        thread.start()
        server = build_server(self, stop_event)
        if open_browser:
            webbrowser.open(f"http://{self.config.server_host}:{self.config.server_port}")
        try:
            server.serve_forever()
        finally:
            stop_event.set()
            server.server_close()
