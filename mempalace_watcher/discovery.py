from __future__ import annotations

from pathlib import Path
import os
from typing import Iterable

from .config import AppConfig
from .core import ProjectRecord, normalize_path


def _is_ignored(path: Path, ignored: set[str]) -> bool:
    normalized = normalize_path(path)
    return any(normalized == item or normalized.startswith(item + os.sep) for item in ignored)


def _is_project_root(path: Path) -> bool:
    return any(
        (path / marker).exists()
        for marker in (
            ".mempalace",
            ".mempalace-data",
            ".venv-mempalace",
            "scripts/mempalace_refresh.ps1",
            "scripts/mempalace_query.ps1",
            "scripts/mempalace_wakeup.ps1",
        )
    )


def _project_marker_path(path: Path) -> Path:
    for marker in (
        ".mempalace",
        ".mempalace-data",
        ".venv-mempalace",
        "scripts/mempalace_refresh.ps1",
        "scripts/mempalace_query.ps1",
        "scripts/mempalace_wakeup.ps1",
    ):
        candidate = path / marker
        if candidate.exists():
            return candidate
    return path / "memory.md"


def discover_projects(config: AppConfig) -> list[ProjectRecord]:
    ignored = {normalize_path(Path(item)) for item in config.ignore_paths}
    results: list[ProjectRecord] = []
    seen: set[str] = set()

    for root_value in config.project_roots:
        root = Path(root_value)
        if not root.exists():
            continue

        for current, dirnames, _filenames in os.walk(root):
            current_path = Path(current).resolve()
            if _is_ignored(current_path, ignored):
                dirnames[:] = []
                continue

            dirnames[:] = [
                dirname
                for dirname in dirnames
                if not dirname.startswith(".")
                and not _is_ignored(current_path / dirname, ignored)
                and dirname not in {
                    ".git",
                    ".venv",
                    "__pycache__",
                    "node_modules",
                    "dist",
                    "build",
                    ".next",
                    ".turbo",
                    ".pytest_cache",
                }
            ]

            if not _is_project_root(current_path):
                continue

            normalized = normalize_path(current_path)
            if normalized in seen:
                continue
            seen.add(normalized)
            resolved_path = current_path
            results.append(
                ProjectRecord(
                    path=resolved_path,
                    name=current_path.name,
                    refresh_script=resolved_path / "scripts" / "mempalace_refresh.ps1",
                    marker_path=_project_marker_path(resolved_path),
                )
            )

    results.sort(key=lambda item: (item.name.lower(), normalize_path(item.path)))
    return results
