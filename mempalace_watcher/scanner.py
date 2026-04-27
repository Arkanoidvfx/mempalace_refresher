from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import os
import subprocess
import time
from typing import Iterable

from .config import AppConfig
from .core import (
    CRITICAL_MARKERS,
    ScanResult,
    clamp,
    iso_now,
    is_critical_path,
    parse_iso,
    top_relative_samples,
    utc_now,
)
from .windows import hidden_subprocess_kwargs


@dataclass(slots=True)
class FileChangeEntry:
    path: str
    status: str
    exists: bool
    size: int | None
    mtime_ns: int | None

    def to_record(self) -> dict[str, object]:
        return {
            "path": self.path,
            "status": self.status,
            "exists": self.exists,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
        }


@dataclass(slots=True)
class FileChangeSnapshot:
    changed_entries: list[FileChangeEntry]
    changed_paths: list[str]
    change_count: int
    critical_change_count: int

    def to_records(self) -> list[dict[str, object]]:
        return [entry.to_record() for entry in self.changed_entries]


IGNORED_SCAN_DIRS = {
    ".mempalace",
    ".mempalace-data",
    ".mempalace-home",
    ".venv-mempalace",
    ".tmp",
    ".cache",
}


def _ignored_prefixes(root: Path, config: AppConfig) -> set[str]:
    prefixes = {str((root / name).resolve()).lower() for name in IGNORED_SCAN_DIRS}
    prefixes.update(str(Path(item).resolve()).lower() for item in config.ignore_paths)
    return prefixes


def _is_ignored_path(path: Path, prefixes: set[str]) -> bool:
    normalized = str(path.resolve()).lower()
    return any(normalized == item or normalized.startswith(item + os.sep) for item in prefixes)


def _is_ignored_relative(relative_path: str) -> bool:
    lowered = relative_path.replace("\\", "/").lower()
    parts = lowered.split("/")
    return any(part in IGNORED_SCAN_DIRS for part in parts) or lowered.startswith(".mempalace")


def _normalize_relative_path(relative_path: str) -> str:
    return relative_path.replace("\\", "/")


def _entry_key(relative_path: str) -> str:
    return _normalize_relative_path(relative_path).lower()


def _entry_record(entry: FileChangeEntry) -> dict[str, object]:
    return {
        "path": _normalize_relative_path(entry.path),
        "status": entry.status,
        "exists": bool(entry.exists),
        "size": entry.size,
        "mtime_ns": entry.mtime_ns,
    }


def _baseline_index(accepted_change_snapshot: list[dict[str, object]] | None) -> dict[str, dict[str, object]]:
    if not accepted_change_snapshot:
        return {}
    index: dict[str, dict[str, object]] = {}
    for item in accepted_change_snapshot:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        normalized = {
            "path": _normalize_relative_path(path),
            "status": str(item.get("status") or ""),
            "exists": bool(item.get("exists")),
            "size": None if item.get("size") is None else int(item["size"]),
            "mtime_ns": None if item.get("mtime_ns") is None else int(item["mtime_ns"]),
        }
        index[_entry_key(path)] = normalized
    return index


def _git_changed_entries(root: Path, prefixes: set[str]) -> list[FileChangeEntry] | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-uall"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if proc.returncode != 0:
        return None

    output: list[FileChangeEntry] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        payload = line[3:].strip()
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        if _is_ignored_relative(payload):
            continue
        candidate = root / payload
        if _is_ignored_path(candidate, prefixes):
            continue
        exists = candidate.exists()
        size: int | None = None
        mtime_ns: int | None = None
        if exists and "D" not in status:
            try:
                stat_result = candidate.stat()
                size = stat_result.st_size
                mtime_ns = stat_result.st_mtime_ns
            except OSError:
                exists = False
        output.append(
            FileChangeEntry(
                path=_normalize_relative_path(payload),
                status=status,
                exists=exists,
                size=size,
                mtime_ns=mtime_ns,
            )
        )
    return output


def _filesystem_changed_entries(root: Path, last_refresh: str | None, prefixes: set[str]) -> list[FileChangeEntry]:
    anchor = parse_iso(last_refresh)
    if anchor is None:
        return []

    changed: list[FileChangeEntry] = []
    anchor_ts = anchor.timestamp()
    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in {
                ".git",
                ".venv",
                ".mempalace",
                ".mempalace-data",
                ".mempalace-home",
                ".venv-mempalace",
                ".tmp",
                ".cache",
                "__pycache__",
                "node_modules",
                "dist",
                "build",
                ".next",
                ".turbo",
                ".pytest_cache",
                ".mypy_cache",
            }
            and not _is_ignored_path(current_path / dirname, prefixes)
        ]
        for filename in filenames:
            file_path = current_path / filename
            try:
                if _is_ignored_path(file_path, prefixes):
                    continue
                if file_path.stat().st_mtime > anchor_ts:
                    stat_result = file_path.stat()
                    changed.append(
                        FileChangeEntry(
                            path=_normalize_relative_path(str(file_path.relative_to(root))),
                            status="M",
                            exists=True,
                            size=stat_result.st_size,
                            mtime_ns=stat_result.st_mtime_ns,
                        )
                    )
            except OSError:
                continue
    return changed


def collect_change_snapshot(root: Path, last_refresh: str | None, config: AppConfig) -> FileChangeSnapshot:
    prefixes = _ignored_prefixes(root, config)
    git_entries = _git_changed_entries(root, prefixes)
    if git_entries is None:
        git_entries = _filesystem_changed_entries(root, last_refresh, prefixes)
    changed_paths = [entry.path for entry in git_entries]
    change_count = len(git_entries)
    critical_change_count = sum(1 for item in changed_paths if is_critical_path(item))
    return FileChangeSnapshot(
        changed_entries=git_entries,
        changed_paths=changed_paths,
        change_count=change_count,
        critical_change_count=critical_change_count,
    )


def _changed_snapshot(root: Path, last_refresh: str | None, config: AppConfig) -> FileChangeSnapshot:
    return collect_change_snapshot(root, last_refresh, config)


def _filter_accepted_entries(
    entries: list[FileChangeEntry],
    accepted_change_snapshot: list[dict[str, object]] | None,
) -> list[FileChangeEntry]:
    accepted = _baseline_index(accepted_change_snapshot)
    if not accepted:
        return entries

    filtered: list[FileChangeEntry] = []
    for entry in entries:
        current_record = _entry_record(entry)
        baseline_record = accepted.get(_entry_key(entry.path))
        if baseline_record == current_record:
            continue
        filtered.append(entry)
    return filtered


def _calculate_drift(
    *,
    age_hours: float,
    change_count: int,
    critical_change_count: int,
    last_status: str | None,
    last_error: str | None,
    paused: bool,
    has_refresh_history: bool,
    config: AppConfig,
) -> tuple[int, str, list[str]]:
    if paused:
        return 0, "paused", ["paused by user"]

    reasons: list[str] = []
    if not has_refresh_history:
        reasons.append("no successful refresh yet")
    age_points = clamp(int(age_hours / 3 * 5), 0, 40)
    error_points = 25 if last_status == "error" or last_error else 0
    change_points = clamp(change_count * 5, 0, 35)
    critical_points = clamp(critical_change_count * 5, 0, 15)

    if has_refresh_history and age_hours >= config.stale_threshold_hours:
        reasons.append(f"refresh is {age_hours:.1f}h old")
    elif has_refresh_history and age_hours > 0:
        reasons.append(f"refresh is {age_hours:.1f}h old")

    if change_count:
        reasons.append(f"{change_count} changed file(s)")
    if critical_change_count:
        reasons.append(f"{critical_change_count} critical change(s)")
    if last_error:
        reasons.append("last refresh failed")

    score = clamp(age_points + change_points + critical_points + error_points, 0, 100)
    if last_status == "error" or last_error:
        status = "error"
    elif not has_refresh_history:
        status = "needs refresh"
    elif score >= config.refresh_threshold:
        status = "needs refresh"
    elif score >= max(20, config.refresh_threshold // 2):
        status = "stale"
    else:
        status = "fresh"

    if not reasons:
        reasons.append("no significant drift detected")

    return score, status, reasons


def scan_project(
    *,
    root: Path,
    name: str,
    last_refresh: str | None,
    last_status: str | None,
    last_error: str | None,
    paused: bool,
    config: AppConfig,
    accepted_change_snapshot: list[dict[str, object]] | None = None,
) -> tuple[ScanResult, list[str]]:
    now = utc_now()
    anchor = parse_iso(last_refresh)
    has_refresh_history = anchor is not None
    if anchor is None:
        age_hours = float(config.stale_threshold_hours + 24)
    else:
        age_hours = max(0.0, (now - anchor).total_seconds() / 3600.0)

    snapshot = collect_change_snapshot(root, last_refresh, config)
    accepted_entries = _filter_accepted_entries(snapshot.changed_entries, accepted_change_snapshot)
    changed_paths = [entry.path for entry in accepted_entries]
    change_count = len(accepted_entries)
    critical_change_count = sum(1 for item in changed_paths if is_critical_path(item))
    drift_score, status, reasons = _calculate_drift(
        age_hours=age_hours,
        change_count=change_count,
        critical_change_count=critical_change_count,
        last_status=last_status,
        last_error=last_error,
        paused=paused,
        has_refresh_history=has_refresh_history,
        config=config,
    )
    samples = top_relative_samples(changed_paths)
    result = ScanResult(
        path=root,
        name=name,
        status=status,
        drift_score=drift_score,
        change_count=change_count,
        critical_change_count=critical_change_count,
        age_hours=age_hours,
        reasons=reasons,
        changed_samples=samples,
        last_refresh=last_refresh,
        last_seen=iso_now(),
        paused=paused,
        error=last_error if status == "error" else None,
    )
    return result, samples
