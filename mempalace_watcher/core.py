from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
import os


IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".pytest_cache",
    ".mypy_cache",
    ".idea",
}

CRITICAL_MARKERS = (
    "memory.md",
    ".mempalace",
    "readme",
    "docs",
    "src",
    "config",
    "scripts",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def normalize_path(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(value)))


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_critical_path(relative_path: str) -> bool:
    lowered = relative_path.replace("\\", "/").lower()
    if lowered.endswith("memory.md"):
        return True
    if lowered.endswith(".mempalace"):
        return True
    parts = lowered.split("/")
    return any(marker in parts or marker in lowered for marker in CRITICAL_MARKERS)


@dataclass(slots=True)
class ProjectRecord:
    path: Path
    name: str
    refresh_script: Path
    marker_path: Path


@dataclass(slots=True)
class ScanResult:
    path: Path
    name: str
    status: str
    drift_score: int
    change_count: int
    critical_change_count: int
    age_hours: float
    reasons: list[str] = field(default_factory=list)
    changed_samples: list[str] = field(default_factory=list)
    last_refresh: str | None = None
    last_seen: str | None = None
    paused: bool = False
    error: str | None = None


def split_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


def unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def top_relative_samples(paths: Sequence[str], limit: int = 5) -> list[str]:
    samples = [path.replace("\\", "/") for path in paths[:limit]]
    return unique_preserve_order(samples)

