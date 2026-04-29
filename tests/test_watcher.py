from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
import time
from unittest.mock import patch

from mempalace_watcher.config import AppConfig
from mempalace_watcher.desktop import _listener_pids, run_desktop
from mempalace_watcher.web import build_server
from mempalace_watcher.discovery import discover_projects
from mempalace_watcher.core import iso_now
from mempalace_watcher.scanner import _changed_snapshot, scan_project
from mempalace_watcher.service import WatcherService
from mempalace_watcher.windows import hidden_subprocess_kwargs


class WatcherTests(unittest.TestCase):
    def make_project(self, base: Path, name: str = "Demo") -> Path:
        root = base / name
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "mempalace_refresh.ps1").write_text("Write-Host 'refresh'\n", encoding="utf-8")
        (root / ".mempalace").mkdir()
        (root / "src").mkdir()
        (root / "src" / "app.txt").write_text("hello\n", encoding="utf-8")
        return root

    def test_discovery_finds_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.make_project(base)
            config = AppConfig(project_roots=[tmp], ignore_paths=[])
            projects = discover_projects(config)
            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0].path.name, "Demo")

    def test_default_config_is_safe_for_shared_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state" / "config.json"
            config = AppConfig()
            self.assertEqual(config.project_roots, [])
            self.assertEqual(config.ignore_paths, [])
            self.assertFalse(path.exists())

    def test_discovery_finds_marker_only_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "MarkerOnly"
            root.mkdir()
            (root / ".mempalace").mkdir()
            config = AppConfig(project_roots=[tmp], ignore_paths=[])
            projects = discover_projects(config)
            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0].path.name, "MarkerOnly")

    def test_scan_scores_critical_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text("changed\n", encoding="utf-8")
            config = AppConfig(project_roots=[tmp], ignore_paths=[], refresh_threshold=40, stale_threshold_hours=24)
            result, _ = scan_project(
                root=root,
                name="Demo",
                last_refresh=None,
                last_status=None,
                last_error=None,
                paused=False,
                config=config,
            )
            self.assertIn(result.status, {"stale", "needs refresh"})
            self.assertGreater(result.drift_score, 0)
            self.assertGreaterEqual(result.change_count, 0)

    def test_scan_ignores_mempalace_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            config = AppConfig(project_roots=[tmp], ignore_paths=[])
            fake = unittest.mock.MagicMock(return_value=unittest.mock.MagicMock(returncode=0, stdout="\n".join([
                "?? .mempalace-data/cache.txt",
                " M src/app.txt",
            ]), stderr=""))
            with patch("mempalace_watcher.scanner.subprocess.run", fake):
                snapshot = _changed_snapshot(root, None, config)
            self.assertEqual(snapshot.change_count, 1)
            self.assertEqual(snapshot.changed_paths, ["src/app.txt"])

    def test_scan_ignores_entries_matching_accepted_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            config = AppConfig(project_roots=[tmp], ignore_paths=[])
            fake = unittest.mock.MagicMock(
                return_value=unittest.mock.MagicMock(returncode=0, stdout=" M src/app.txt\n", stderr="")
            )
            baseline = [
                {
                    "path": "src/app.txt",
                    "status": " M",
                    "exists": True,
                    "size": (root / "src" / "app.txt").stat().st_size,
                    "mtime_ns": (root / "src" / "app.txt").stat().st_mtime_ns,
                }
            ]
            with patch("mempalace_watcher.scanner.subprocess.run", fake):
                snapshot = _changed_snapshot(root, iso_now(), config)
                result, _ = scan_project(
                    root=root,
                    name="Demo",
                    last_refresh=iso_now(),
                    last_status="fresh",
                    last_error=None,
                    paused=False,
                    config=config,
                    accepted_change_snapshot=baseline,
                )
            self.assertEqual(snapshot.change_count, 1)
            self.assertEqual(snapshot.changed_paths, ["src/app.txt"])
            self.assertEqual(result.change_count, 0)
            self.assertEqual(result.changed_samples, [])

    def test_scan_reports_changes_after_successful_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            for idx in range(5):
                target = root / "src" / f"changed_{idx}.txt"
                target.write_text(f"changed {idx}\n", encoding="utf-8")
                os.utime(target, (time.time() + 3600, time.time() + 3600))
            config = AppConfig(project_roots=[tmp], ignore_paths=[])
            fake = unittest.mock.MagicMock(
                return_value=unittest.mock.MagicMock(
                    returncode=0,
                    stdout="\n".join([f" M src/changed_{idx}.txt" for idx in range(5)]) + "\n",
                    stderr="",
                )
            )
            with patch("mempalace_watcher.scanner.subprocess.run", fake):
                result, _ = scan_project(
                    root=root,
                    name="Demo",
                    last_refresh=iso_now(),
                    last_status="fresh",
                    last_error=None,
                    paused=False,
                    config=config,
                )
            self.assertIn(result.status, {"stale", "needs refresh"})
            self.assertGreaterEqual(result.drift_score, 0)
            self.assertEqual(result.change_count, 5)

    def test_refresh_persists_accepted_change_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            proc = unittest.mock.MagicMock()
            proc.stdout = iter(())
            proc.returncode = 0
            proc.wait.return_value = 0
            proc.kill.return_value = None
            baseline = [
                {
                    "path": "project_assets/docs/ARCHIVED_IMPORTANT_INFO.md",
                    "status": " D",
                    "exists": False,
                    "size": None,
                    "mtime_ns": None,
                }
            ]

            fake_scan_result = unittest.mock.MagicMock(
                status="fresh",
                drift_score=0,
                change_count=0,
                critical_change_count=0,
                age_hours=0.0,
                error=None,
                reasons=[],
                changed_samples=[],
            )
            with patch("mempalace_watcher.service.subprocess.Popen", return_value=proc), patch(
                "mempalace_watcher.service.collect_change_snapshot"
            ) as collect_snapshot, patch("mempalace_watcher.service.scan_project", return_value=(fake_scan_result, [])) as scan_run, patch(
                "mempalace_watcher.service.time.perf_counter", side_effect=[100.0, 160.0]
            ):
                collect_snapshot.return_value = unittest.mock.MagicMock(to_records=lambda: baseline)
                service.refresh_project(str(root))

            row = service.db.get_project(str(root))
            self.assertIsNotNone(row)
            self.assertEqual(json.loads(row["accepted_change_snapshot_json"]), baseline)
            self.assertIsNotNone(row["accepted_change_snapshot_at"])
            self.assertEqual(scan_run.call_args.kwargs["accepted_change_snapshot"], baseline)

    def test_refresh_updates_state_in_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            proc = unittest.mock.MagicMock()
            proc.stdout = iter(())
            proc.returncode = 0
            proc.wait.return_value = 0
            proc.kill.return_value = None
            scan_run = unittest.mock.MagicMock(return_value=unittest.mock.MagicMock(returncode=0, stdout="", stderr=""))
            with patch("mempalace_watcher.service.subprocess.Popen", return_value=proc), patch(
                "mempalace_watcher.service.time.perf_counter", side_effect=[100.0, 160.0]
            ), patch("mempalace_watcher.scanner.subprocess.run", scan_run):
                result = service.refresh_project(str(root))
            self.assertEqual(result.status, "fresh")
            row = service.db.get_project(str(root))
            self.assertIsNotNone(row)
            self.assertEqual(row["last_status"], "fresh")
            self.assertEqual(row["refresh_count"], 1)
            self.assertEqual(row["last_refresh_duration_ms"], 60000)
            self.assertEqual(row["refresh_avg_duration_ms"], 60000)
            self.assertIsNotNone(row["accepted_change_snapshot_json"])

    def test_refresh_duration_prediction_uses_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            proc = unittest.mock.MagicMock()
            proc.stdout = iter(())
            proc.returncode = 0
            proc.wait.return_value = 0
            proc.kill.return_value = None
            scan_run = unittest.mock.MagicMock(return_value=unittest.mock.MagicMock(returncode=0, stdout="", stderr=""))
            with patch("mempalace_watcher.service.subprocess.Popen", return_value=proc), patch(
                "mempalace_watcher.scanner.subprocess.run", scan_run
            ), patch("mempalace_watcher.service.time.perf_counter", side_effect=[100.0, 130.0, 200.0, 260.0]):
                service.refresh_project(str(root))
                service.refresh_project(str(root))
            row = service.db.get_project(str(root))
            self.assertEqual(row["refresh_count"], 2)
            self.assertEqual(row["last_refresh_duration_ms"], 60000)
            self.assertEqual(row["refresh_avg_duration_ms"], 45000)

    def test_refresh_uses_completion_timestamp_as_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            proc = unittest.mock.MagicMock()
            proc.stdout = iter(())
            proc.returncode = 0
            proc.wait.return_value = 0
            proc.kill.return_value = None
            fake_result = unittest.mock.MagicMock()
            fake_result.status = "pending"
            fake_result.drift_score = 123
            fake_result.change_count = 9
            fake_result.critical_change_count = 4
            fake_result.age_hours = 12.0
            fake_result.error = None
            fake_result.reasons = []
            fake_result.changed_samples = []
            timestamps = [
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:05:00+00:00",
            ]

            def fake_iso_now() -> str:
                return timestamps.pop(0) if timestamps else "2026-01-01T00:05:00+00:00"

            scan_run = unittest.mock.MagicMock(return_value=(fake_result, []))
            baseline_snapshot = []
            with patch("mempalace_watcher.service.subprocess.Popen", return_value=proc), patch(
                "mempalace_watcher.service.collect_change_snapshot"
            ) as collect_snapshot, patch("mempalace_watcher.service.scan_project", scan_run
            ), patch("mempalace_watcher.service.iso_now", side_effect=fake_iso_now):
                collect_snapshot.return_value = unittest.mock.MagicMock(to_records=lambda: baseline_snapshot)
                result = service.refresh_project(str(root))
            self.assertEqual(result.status, "fresh")
            self.assertEqual(scan_run.call_args.kwargs["last_refresh"], "2026-01-01T00:05:00+00:00")
            row = service.db.get_project(str(root))
            self.assertIsNotNone(row)
            self.assertEqual(row["last_refresh"], "2026-01-01T00:05:00+00:00")
            self.assertEqual(row["change_count"], 0)

    def test_refresh_streams_progress_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            proc = unittest.mock.MagicMock()
            proc.stdout = iter(
                [
                    "Creating project-local virtual environment: C:\\repo\\.venv-mempalace\n",
                    "Installing mempalace>=3.1,<4 into project-local virtual environment...\n",
                    "Rebuilding palace from curated staging corpus: C:\\repo\\.mempalace\\palace\n",
                ]
            )
            proc.returncode = 0
            proc.wait.return_value = 0
            proc.kill.return_value = None
            scan_run = unittest.mock.MagicMock(return_value=unittest.mock.MagicMock(returncode=0, stdout="", stderr=""))
            with patch("mempalace_watcher.service.subprocess.Popen", return_value=proc), patch(
                "mempalace_watcher.scanner.subprocess.run", scan_run
            ):
                service.refresh_project(str(root))
            state = service.refresh_state(str(root))
            self.assertTrue(state["done"])
            self.assertEqual(state["percent"], 100)
            self.assertEqual(state["phase"], "Complete")

    def test_project_detail_includes_full_log_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            for idx in range(10):
                service.db.log_event(
                    path=str(root),
                    kind="scan" if idx % 2 == 0 else "refresh",
                    status="success",
                    message=f"event {idx}",
                    duration_ms=100 + idx,
                )
            detail = service.project_detail(str(root))
            self.assertEqual(len(detail["events"]), 10)
            self.assertIsInstance(detail["log_lines"], list)
            self.assertGreater(len(detail["log_lines"]), len(detail["events"]))
            self.assertIn("Recent events (newest first):", detail["log_text"])
            self.assertIn("event 9", detail["log_text"])

    def test_resolve_powershell_prefers_pwsh_exe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            service = WatcherService(base)
            with patch("mempalace_watcher.service.shutil.which") as which, patch(
                "mempalace_watcher.service.subprocess.run"
            ):
                which.side_effect = lambda name: r"C:\\Program Files\\PowerShell\\7\\pwsh.exe" if name in {"pwsh.exe", "pwsh"} else None
                resolved = service._resolve_powershell()
            self.assertEqual(resolved, r"C:\\Program Files\\PowerShell\\7\\pwsh.exe")

    def test_resolve_powershell_raises_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            service = WatcherService(base)
            with patch("mempalace_watcher.service.shutil.which", return_value=None):
                with self.assertRaises(FileNotFoundError):
                    service._resolve_powershell()

    def test_build_server_supports_ephemeral_port_for_desktop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            service = WatcherService(base)
            stop_event = unittest.mock.MagicMock()
            server = build_server(service, stop_event, port=0)
            try:
                self.assertNotEqual(server.server_address[1], 0)
                self.assertTrue(server.daemon_threads)
                self.assertFalse(server.block_on_close)
            finally:
                server.server_close()

    def test_service_uses_state_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            service = WatcherService(base)
            self.assertEqual(service.config_path, base / "state" / "config.json")
            self.assertTrue(service.config_path.exists())
            self.assertEqual(service.config.project_roots, [])

    def test_load_config_migrates_legacy_repo_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            legacy_path = base / "config.json"
            state_path = base / "state" / "config.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "project_roots": ["D:\\Projects\\Legacy"],
                        "ignore_paths": ["D:\\Projects\\Legacy\\.venv"],
                        "stale_threshold_hours": 24,
                        "refresh_threshold": 45,
                        "watch_interval_seconds": 300,
                        "server_host": "127.0.0.1",
                        "server_port": 8787,
                        "auto_refresh": False,
                        "refresh_timeout_seconds": 3600,
                    }
                ),
                encoding="utf-8",
            )
            service = WatcherService(base)
            self.assertEqual(service.config.project_roots, ["D:\\Projects\\Legacy"])
            self.assertTrue(state_path.exists())

    def test_hidden_subprocess_kwargs_windows_shape(self) -> None:
        with patch("mempalace_watcher.windows.os.name", "nt"), patch(
            "mempalace_watcher.windows.subprocess.CREATE_NO_WINDOW", 134217728, create=True
        ), patch("mempalace_watcher.windows.subprocess.STARTF_USESHOWWINDOW", 1, create=True), patch(
            "mempalace_watcher.windows.subprocess.SW_HIDE", 0, create=True
        ), patch("mempalace_watcher.windows.subprocess.STARTUPINFO", create=True) as startupinfo_cls:
            startupinfo = unittest.mock.MagicMock()
            startupinfo.dwFlags = 0
            startupinfo_cls.return_value = startupinfo
            kwargs = hidden_subprocess_kwargs()
        self.assertEqual(kwargs["creationflags"], 134217728)
        self.assertIs(kwargs["startupinfo"], startupinfo)
        self.assertEqual(startupinfo.dwFlags, 1)
        self.assertEqual(startupinfo.wShowWindow, 0)

    def test_scanner_git_status_uses_hidden_windows_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            config = AppConfig(project_roots=[tmp], ignore_paths=[])
            fake_proc = unittest.mock.MagicMock(returncode=0, stdout="", stderr="")
            with patch("mempalace_watcher.scanner.subprocess.run", return_value=fake_proc) as run_mock, patch(
                "mempalace_watcher.scanner.hidden_subprocess_kwargs", return_value={"creationflags": 123}
            ):
                _changed_snapshot(root, None, config)
            self.assertEqual(run_mock.call_args.kwargs["creationflags"], 123)

    def test_refresh_uses_hidden_windows_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            proc = unittest.mock.MagicMock()
            proc.stdout = iter(())
            proc.returncode = 0
            proc.wait.return_value = 0
            proc.kill.return_value = None
            scan_run = unittest.mock.MagicMock(return_value=unittest.mock.MagicMock(returncode=0, stdout="", stderr=""))
            with patch("mempalace_watcher.service.subprocess.Popen", return_value=proc) as popen_mock, patch(
                "mempalace_watcher.service.hidden_subprocess_kwargs", return_value={"creationflags": 456}
            ), patch("mempalace_watcher.scanner.subprocess.run", scan_run):
                service.refresh_project(str(root))
            self.assertEqual(popen_mock.call_args.kwargs["creationflags"], 456)

    def test_listener_pids_uses_hidden_windows_launch(self) -> None:
        fake_proc = unittest.mock.MagicMock(returncode=0, stdout="", stderr="")
        with patch("mempalace_watcher.desktop.subprocess.run", return_value=fake_proc) as run_mock, patch(
            "mempalace_watcher.desktop.hidden_subprocess_kwargs", return_value={"creationflags": 789}
        ):
            _listener_pids(8787)
        self.assertEqual(run_mock.call_args.kwargs["creationflags"], 789)

    def test_run_desktop_creates_window_with_focus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            fake_window = unittest.mock.MagicMock()
            fake_window.events.closed = unittest.mock.MagicMock()
            fake_server = unittest.mock.MagicMock()
            fake_server.server_address = ("127.0.0.1", 8787)
            webview_mock = unittest.mock.MagicMock()
            webview_mock.create_window.return_value = fake_window
            with patch("mempalace_watcher.desktop.build_server", return_value=fake_server), patch(
                "mempalace_watcher.desktop._release_dashboard_port"
            ), patch("mempalace_watcher.desktop._set_taskbar_identity"), patch(
                "mempalace_watcher.desktop._wait_for_server"
            ), patch("mempalace_watcher.desktop.Thread") as thread_cls, patch.dict(
                "sys.modules", {"webview": webview_mock}
            ):
                thread_cls.return_value.start.return_value = None
                run_desktop(service)
            self.assertTrue(webview_mock.create_window.call_args.kwargs["focus"])

    def test_refresh_without_script_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "MarkerOnly"
            root.mkdir()
            (root / ".mempalace").mkdir()
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            result = service.refresh_project(str(root))
            self.assertEqual(result.status, "error")
            self.assertIn("missing", (result.error or "").lower())

    def test_refresh_all_projects_calls_each_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root_a = self.make_project(base, "One")
            root_b = self.make_project(base, "Two")
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            with patch.object(service, "refresh_project") as refresh:
                service.refresh_all_projects()
            self.assertEqual(refresh.call_count, 2)
            self.assertEqual({call.args[0] for call in refresh.call_args_list}, {str(root_a), str(root_b)})

    def test_rescan_all_apply_refresh_starts_each_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root_a = self.make_project(base, "One")
            root_b = self.make_project(base, "Two")
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            with patch.object(service, "start_refresh_project") as start_refresh:
                service.rescan_all(apply_refresh=True)
            self.assertEqual(start_refresh.call_count, 2)
            self.assertEqual({call.args[0] for call in start_refresh.call_args_list}, {str(root_a), str(root_b)})

    def test_refresh_progress_parser_maps_stage_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = WatcherService(Path(tmp))
            percent, phase = service._infer_refresh_progress(
                "Installing mempalace>=3.1,<4 into project-local virtual environment...",
                40,
            )
            self.assertGreaterEqual(percent, 70)
            self.assertEqual(phase, "Installing MemPalace")

    def test_start_refresh_project_sets_running_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            with patch("mempalace_watcher.service.Thread.start") as thread_start:
                thread_start.return_value = None
                state = service.start_refresh_project(str(root))
            self.assertTrue(state["active"])
            self.assertEqual(state["phase"], "Running")

    def test_start_scan_project_sets_running_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.make_project(base)
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            with patch("mempalace_watcher.service.Thread.start") as thread_start:
                thread_start.return_value = None
                state = service.start_scan_project(str(root))
            self.assertTrue(state["active"])
            self.assertEqual(state["phase"], "Starting scan")
            self.assertIn("Preparing", state["message"])

    def test_start_refresh_all_projects_starts_each_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.make_project(base, "One")
            self.make_project(base, "Two")
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            started: list[str] = []

            def fake_start(path: str, dry_run: bool = False):
                started.append(path)
                return {"active": True, "phase": "Running"}

            with patch.object(service, "start_refresh_project", side_effect=fake_start):
                result = service.start_refresh_all_projects()
            self.assertEqual(result["ok"], True)
            self.assertEqual(len(started), 2)
            self.assertEqual(set(started), {str(base / "One"), str(base / "Two")})

    def test_start_refresh_all_projects_does_not_rediscover(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.make_project(base, "One")
            self.make_project(base, "Two")
            service = WatcherService(base)
            service.save_config(AppConfig(project_roots=[tmp], ignore_paths=[]))
            service.discover()
            with patch.object(service, "discover") as discover, patch.object(service, "start_refresh_project") as start_refresh:
                start_refresh.side_effect = lambda path, dry_run=False: {"active": True, "phase": "Running"}
                result = service.start_refresh_all_projects()
            self.assertEqual(result["ok"], True)
            discover.assert_not_called()
            self.assertEqual(start_refresh.call_count, 2)

    def test_start_scan_sets_running_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = WatcherService(Path(tmp))
            with patch("mempalace_watcher.service.Thread.start") as thread_start:
                thread_start.return_value = None
                state = service.start_scan()
            self.assertTrue(state["active"])
            self.assertEqual(state["phase"], "Discovering")


if __name__ == "__main__":
    unittest.main()
