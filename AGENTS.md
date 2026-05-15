# AGENTS.md

## Scope

These instructions apply to the `D:\Projects\MemPalace_Watcher` repository.

## Project Context

- This project is the local dashboard/watcher for MemPalace-enabled repositories.
- It is a stdlib-first Python app with SQLite state, a local HTTP dashboard, and optional `pywebview` desktop mode.
- Read `memory.md` before meaningful work and update it after meaningful repository changes.
- Keep machine-local runtime state in `state/`; do not commit user-specific `state/config.json` or SQLite runtime data.

## Python

- Use the project-local `.venv`.
- Do not install dependencies into system/global Python.
- Prefer:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m py_compile mempalace_watcher\*.py tests\test_watcher.py
```

## Refresh Behavior

- Dashboard refresh should invoke project `scripts\mempalace_refresh.ps1` in incremental mode.
- Do not make routine Watcher refreshes delete `.mempalace\palace`; live MCP servers can hold ChromaDB files open on Windows.
- Clean rebuilds are explicit maintenance operations and require stopping live MCP/Codex processes first.

## UI / Dashboard Guardrails

- Keep refresh state and scan state separate.
- Do not rebuild the projects table while a row menu is open.
- Escape Windows paths before embedding them in generated JavaScript.
- Preserve responsive click feedback for refresh/scan actions.

## Validation

- For Python/service changes, run the full unittest suite.
- For dashboard HTML/JS generation changes, also verify generated script validity when relevant.
- For doc-only changes, tests are optional; say when they were not run.
