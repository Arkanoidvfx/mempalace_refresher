from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator, Sequence

from .core import iso_now


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS projects (
    path TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    marker_path TEXT NOT NULL,
    refresh_script TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    last_seen TEXT,
    last_refresh TEXT,
    last_status TEXT NOT NULL DEFAULT 'new',
    last_error TEXT,
    drift_score INTEGER NOT NULL DEFAULT 0,
    change_count INTEGER NOT NULL DEFAULT 0,
    critical_change_count INTEGER NOT NULL DEFAULT 0,
    age_hours REAL NOT NULL DEFAULT 0,
    refresh_count INTEGER NOT NULL DEFAULT 0,
    last_refresh_duration_ms INTEGER,
    refresh_avg_duration_ms INTEGER,
    accepted_change_snapshot_json TEXT,
    accepted_change_snapshot_at TEXT,
    paused INTEGER NOT NULL DEFAULT 0,
    last_reason TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_path_created_at
    ON events(path, created_at DESC);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_project_columns(conn)

    def _ensure_project_columns(self, conn: sqlite3.Connection) -> None:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(projects)")}
        for column_def in (
            "refresh_count INTEGER NOT NULL DEFAULT 0",
            "last_refresh_duration_ms INTEGER",
            "refresh_avg_duration_ms INTEGER",
            "accepted_change_snapshot_json TEXT",
            "accepted_change_snapshot_at TEXT",
        ):
            name = column_def.split()[0]
            if name not in existing:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {column_def}")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_project(
        self,
        *,
        path: str,
        name: str,
        marker_path: str,
        refresh_script: str,
        last_seen: str | None = None,
    ) -> None:
        now = iso_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    path, name, marker_path, refresh_script, discovered_at,
                    last_seen, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    name=excluded.name,
                    marker_path=excluded.marker_path,
                    refresh_script=excluded.refresh_script,
                    last_seen=COALESCE(excluded.last_seen, projects.last_seen),
                    updated_at=excluded.updated_at
                """,
                (path, name, marker_path, refresh_script, now, last_seen, now),
            )

    def set_paused(self, path: str, paused: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE projects SET paused=?, updated_at=? WHERE path=?",
                (1 if paused else 0, iso_now(), path),
            )

    def update_scan_state(
        self,
        *,
        path: str,
        last_seen: str,
        last_refresh: str | None,
        last_status: str,
        drift_score: int,
        change_count: int,
        critical_change_count: int,
        age_hours: float,
        last_error: str | None,
        last_reason: str | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE projects SET
                    last_seen=?,
                    last_refresh=COALESCE(?, last_refresh),
                    last_status=?,
                    last_error=?,
                    drift_score=?,
                    change_count=?,
                    critical_change_count=?,
                    age_hours=?,
                    last_reason=?,
                    updated_at=?
                WHERE path=?
                """,
                (
                    last_seen,
                    last_refresh,
                    last_status,
                    last_error,
                    drift_score,
                    change_count,
                    critical_change_count,
                    age_hours,
                    last_reason,
                    iso_now(),
                    path,
                ),
            )

    def update_refresh_state(
        self,
        *,
        path: str,
        last_refresh: str,
        last_status: str,
        last_error: str | None,
        drift_score: int,
        change_count: int,
        critical_change_count: int,
        age_hours: float,
        last_reason: str | None,
        refresh_count: int | None = None,
        last_refresh_duration_ms: int | None = None,
        refresh_avg_duration_ms: int | None = None,
        accepted_change_snapshot_json: str | None = None,
        accepted_change_snapshot_at: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE projects SET
                    last_refresh=?,
                    last_status=?,
                    last_error=?,
                    drift_score=?,
                    change_count=?,
                    critical_change_count=?,
                    age_hours=?,
                    refresh_count=COALESCE(?, refresh_count),
                    last_refresh_duration_ms=COALESCE(?, last_refresh_duration_ms),
                    refresh_avg_duration_ms=COALESCE(?, refresh_avg_duration_ms),
                    accepted_change_snapshot_json=COALESCE(?, accepted_change_snapshot_json),
                    accepted_change_snapshot_at=COALESCE(?, accepted_change_snapshot_at),
                    last_reason=?,
                    last_seen=?,
                    updated_at=?
                WHERE path=?
                """,
                (
                    last_refresh,
                    last_status,
                    last_error,
                    drift_score,
                    change_count,
                    critical_change_count,
                    age_hours,
                    refresh_count,
                    last_refresh_duration_ms,
                    refresh_avg_duration_ms,
                    accepted_change_snapshot_json,
                    accepted_change_snapshot_at,
                    last_reason,
                    iso_now(),
                    iso_now(),
                    path,
                ),
            )

    def list_projects(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM projects ORDER BY paused ASC, drift_score DESC, name COLLATE NOCASE"))

    def get_project(self, path: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE path=?", (path,)).fetchone()
            return row

    def prune_projects(self, keep_paths: Sequence[str]) -> int:
        keep = [path for path in keep_paths if path]
        with self.connect() as conn:
            if not keep:
                result = conn.execute("DELETE FROM projects")
                return result.rowcount or 0
            placeholders = ", ".join("?" for _ in keep)
            result = conn.execute(f"DELETE FROM projects WHERE path NOT IN ({placeholders})", tuple(keep))
            return result.rowcount or 0

    def recent_events(self, path: str, limit: int = 25) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM events WHERE path=? ORDER BY created_at DESC LIMIT ?",
                    (path, limit),
                )
            )

    def log_event(
        self,
        *,
        path: str,
        kind: str,
        status: str,
        message: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO events (path, kind, status, message, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (path, kind, status, message, duration_ms, iso_now()),
            )

    def summary(self) -> dict[str, int]:
        counts = {"fresh": 0, "stale": 0, "needs refresh": 0, "error": 0, "paused": 0, "total": 0}
        with self.connect() as conn:
            for row in conn.execute("SELECT last_status, paused FROM projects"):
                counts["total"] += 1
                if row["paused"]:
                    counts["paused"] += 1
                    continue
                status = row["last_status"] or "fresh"
                if status not in counts:
                    counts[status] = 0
                counts[status] += 1
        return counts
