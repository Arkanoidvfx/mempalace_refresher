# MemPalace Watcher

Local watcher for projects that keep `mempalace` data.

## What it does

- discovers projects under configured roots
- stores project state in SQLite
- stores per-user settings locally so tracked folders persist across restarts
- scores staleness/drift from file changes and refresh age
- runs `scripts/mempalace_refresh.ps1` when asked or when the watcher allows it
- serves a local dashboard for quick manual control

## Run

```powershell
python -m mempalace_watcher serve
python -m mempalace_watcher watch
```

Windows launcher scripts:

- `start_dashboard.cmd` creates `.venv` if needed and installs `requirements.txt` into that local environment before launching the desktop dashboard.
- `start_watcher.cmd` launches the background watcher hidden and keeps using the same local `.venv`.

## Config

Shared repo defaults live in `config.example.json`.

Per-user runtime settings live in `state/config.json` and should stay untracked. On first run, the app creates that file automatically. If an older repo-root `config.json` exists, the app migrates it into `state/config.json`.
