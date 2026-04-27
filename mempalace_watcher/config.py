from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import json


DEFAULT_CONFIG = {
    "project_roots": [],
    "ignore_paths": [],
    "stale_threshold_hours": 24,
    "refresh_threshold": 45,
    "watch_interval_seconds": 300,
    "server_host": "127.0.0.1",
    "server_port": 8787,
    "auto_refresh": False,
    "refresh_timeout_seconds": 3600,
}


@dataclass(slots=True)
class AppConfig:
    project_roots: list[str] = field(default_factory=lambda: list(DEFAULT_CONFIG["project_roots"]))
    ignore_paths: list[str] = field(default_factory=lambda: list(DEFAULT_CONFIG["ignore_paths"]))
    stale_threshold_hours: int = DEFAULT_CONFIG["stale_threshold_hours"]
    refresh_threshold: int = DEFAULT_CONFIG["refresh_threshold"]
    watch_interval_seconds: int = DEFAULT_CONFIG["watch_interval_seconds"]
    server_host: str = DEFAULT_CONFIG["server_host"]
    server_port: int = DEFAULT_CONFIG["server_port"]
    auto_refresh: bool = DEFAULT_CONFIG["auto_refresh"]
    refresh_timeout_seconds: int = DEFAULT_CONFIG["refresh_timeout_seconds"]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AppConfig":
        merged = dict(DEFAULT_CONFIG)
        merged.update({key: value for key, value in data.items() if value is not None})
        project_roots = [str(item) for item in merged["project_roots"] if str(item).strip()]
        ignore_paths = [str(item) for item in merged["ignore_paths"] if str(item).strip()]
        return cls(
            project_roots=project_roots,
            ignore_paths=ignore_paths,
            stale_threshold_hours=max(1, int(merged["stale_threshold_hours"])),
            refresh_threshold=max(1, int(merged["refresh_threshold"])),
            watch_interval_seconds=max(10, int(merged["watch_interval_seconds"])),
            server_host=str(merged["server_host"]),
            server_port=max(1, min(65535, int(merged["server_port"]))),
            auto_refresh=bool(merged["auto_refresh"]),
            refresh_timeout_seconds=max(30, int(merged["refresh_timeout_seconds"])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_config(path: Path, legacy_path: Path | None = None) -> AppConfig:
    if not path.exists():
        if legacy_path is not None and legacy_path.exists():
            with legacy_path.open("r", encoding="utf-8") as handle:
                config = AppConfig.from_mapping(json.load(handle))
            save_config(path, config)
            return config
        config = AppConfig()
        save_config(path, config)
        return config
    with path.open("r", encoding="utf-8") as handle:
        return AppConfig.from_mapping(json.load(handle))


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config.to_dict(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
