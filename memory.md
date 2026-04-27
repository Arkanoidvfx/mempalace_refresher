# Memory

## Workspace
- Repository root is the current workspace checkout.
- Project is a local watcher for MemPalace-enabled projects.
- Runtime design is stdlib-only Python with SQLite, a CLI, and a local dashboard.
- Local `.venv` exists in the project root.
- Discovery tracks only real MemPalace projects under configured roots by requiring a top-level `.mempalace`, `.mempalace-data`, `.venv-mempalace`, or `scripts/mempalace_*.ps1` marker, ignores hidden `.mempalace-*` runtime directories, and does not persist the watcher repo itself.

## Project Files
- `config.example.json` is the safe shared template committed with the repo.
- `requirements.txt` currently declares `pywebview` for the desktop dashboard bootstrap.
- `state/config.json` stores per-user project roots, thresholds, and watcher settings; it is local-only and should stay untracked.
- `state/` stores SQLite data and runtime state.
- `start_dashboard.cmd` launches the dashboard from the project-local `.venv`.
- `start_dashboard.cmd` now bootstraps `requirements.txt` into the local `.venv` before launching the hidden desktop dashboard, so a fresh clone can start without manual dependency installation.
- `start_watcher.cmd` now launches the background watcher through `pythonw.exe` and `start_watcher.vbs`, so the watcher starts hidden without leaving a console window open.
- The service now loads config from `state/config.json` and migrates a legacy repo-root `config.json` into that path on first run.
- Shared defaults are now machine-neutral: empty `project_roots` and `ignore_paths`, so a fresh clone starts without leaking the author's local folders.
- `start_dashboard.cmd` now launches a native desktop dashboard via `pywebview` / WebView2; desktop mode clears any stale listener on the configured dashboard port and starts its own ephemeral server for the session.
- `start_dashboard.vbs` is the hidden launcher stub used by `start_dashboard.cmd` so the dashboard starts without keeping a visible console open.
- `mempalace_watcher/windows.py` centralizes hidden Windows subprocess flags; scanner `git`, desktop `netstat` / `taskkill`, and refresh PowerShell launches now use it to avoid popping console windows when the app runs under `pythonw`.
- `icon.ico` is the Windows app icon generated from the repo-root `icon.png`, and desktop mode passes it to `pywebview` so the WebView2 window/taskbar uses the project icon.
- Desktop mode sets an explicit Windows AppUserModelID (`MemPalaceWatcher`) so the taskbar treats the dashboard as its own app instead of a generic Python process.
- Desktop mode now creates the WebView window with `focus=False`, so opening the dashboard does not immediately steal the active window focus.
- Dashboard now has explicit `Refresh selected` and `Refresh all` actions; project refresh runs `.\scripts\mempalace_refresh.ps1` from the project root.
- `Refresh all` now operates on the already tracked project rows instead of re-running discovery synchronously first, so the button responds immediately and the UI can show local busy feedback while per-project refresh jobs start.
- The top-level `Refresh all` button now disables itself and shows `Refreshing all...` while the request is in flight, so the user gets immediate click feedback.
- Dashboard now shows visible action status for refresh/rescan/config saves instead of failing silently.
- Toolbar is now split by responsibility: top bar keeps only `Rescan`, `Refresh all` lives in the Projects panel header, `Save settings` lives in the Settings panel, and the selected-project inspector is read-only.
- Refresh execution resolves a real PowerShell binary via `pwsh.exe` or `powershell.exe` before launching the project script.
- Each successful refresh now stores per-project duration history in SQLite (`refresh_count`, `last_refresh_duration_ms`, `refresh_avg_duration_ms`) and the UI shows `Last`, `Predicted`, and `Runs` for each project.
- Project rows and detail panels label `change_count` as `Pending` to reflect changes not yet refreshed, and scanner now reports the real post-refresh pending diff instead of zeroing it out after a successful run.
- Project change displays now render as `N changed files` plus a separate critical-count line, instead of the ambiguous `N / M critical` format.
- Pending change cells now use a dedicated layout with no word-breaking, so `changed files` and `critical changes` stay readable in the table and inspector.
- Dashboard now polls live refresh state and renders a per-project progress bar; refresh jobs stream stdout into in-memory per-project state, but the UI no longer shows live stdout text.
- Clicking a project refresh now produces immediate optimistic UI feedback: the row highlights, the refresh cell shows `Queued` / `Starting refresh`, and the server state catches up on the next poll.
- Each project row menu now shows a tiny live refresh status badge, and the dashboard polls refresh/project state every 500ms for a snappier bar update.
- Project menus stay open across table rerenders by tracking the open row key in UI state; the earlier flicker came from the 500ms refresh poll rebuilding the table DOM.
- While a project menu is open, the 500ms dashboard poll now refreshes summary state only and skips rebuilding the projects table, so the dropdown stays stable.
- Single-project `Scan changes` now renders as a distinct blue scan progress state in the row progress cell and inspector, auto-selects the scanned project for immediate visibility, and the project menu opens to the left of the trigger button.
- Refresh clicks now also set a local optimistic refresh state so the row shows `Queued` immediately, even before the backend refresh state catches up.
- Row action handlers must use safely escaped JS string literals for Windows paths; raw `onclick` arguments with backslashes can corrupt the project path and make refresh appear stuck on `Idle`.
- `Refresh selected`, `Refresh all`, `Refresh stale`, and auto-refresh start projects in parallel instead of serial queueing.
- Each project row menu now exposes `Refresh memory` and `Scan changes`; the latter runs a single-project scan job and updates the pending-change counts without doing a refresh script run.
- UI guardrails from prior regressions: do not rebuild the projects table while a row menu is open; use safe JS string escaping for Windows paths in inline handlers; keep refresh state and scan state separate so a scan action cannot masquerade as a refresh (or vice versa).
- Dashboard polling policy now prioritizes click responsiveness: summary can update often, but the projects list refreshes only when the UI is idle and not during active pointer/focus interaction in the workspace.
- Refresh baseline is captured at refresh completion, not start, so files written by the refresh script itself do not reappear as pending changes on the next rescan.
- Successful refresh no longer suppresses real post-refresh drift in scanner status; if a rescan still finds changed files, the row should show the real `stale` / `needs refresh` state instead of pretending to be `fresh`.
- Dashboard typography now uses Fira Sans / Fira Code for a more technical, dashboard-oriented look.
- Summary area now uses a hero + metrics layout instead of a flat card strip.
- Project rows now use a compact per-project menu with `Refresh now`, `Pause/Resume`, and `Open folder`; the selected-project panel now includes a collapsible `Project log` drawer with `Copy log` and `Collapse/Expand`.
- Project detail responses now include canonical `log_lines` and `log_text`, and the event history window for project logs is 25 entries instead of the older 8-entry snippet.
- The dashboard HTML generator must escape JS `\n` sequences inside the embedded script; otherwise the browser receives a broken script and the page stays on the empty initial shell.
- Rescan now runs as a background job with a live scan-state object, and the dashboard renders a compact operational scan strip plus current-row highlighting while scan is in progress.
- The desktop dashboard uses `pywebview` with `edgechromium`, which maps to the local WebView2 runtime on Windows.
- Scanner ignores MemPalace runtime/generated paths such as `.mempalace`, `.mempalace-data`, `.mempalace-home`, `.venv-mempalace`, `.tmp`, and `.cache` when counting drift.
- Pending counts now compare the current dirty snapshot against `accepted_change_snapshot_json`; a successful refresh stores the current snapshot as the accepted baseline, so persistent deletions or repo migrations do not reappear after refresh.

## Tracked Projects
- The author's current tracked roots remain only in local `state/config.json` and `state/mempalace_watcher.sqlite3`; they are no longer part of the shared repo defaults.

## Validation
- `python -m py_compile mempalace_watcher\\__init__.py mempalace_watcher\\core.py mempalace_watcher\\config.py mempalace_watcher\\db.py mempalace_watcher\\discovery.py mempalace_watcher\\scanner.py mempalace_watcher\\service.py mempalace_watcher\\web.py mempalace_watcher\\desktop.py mempalace_watcher\\windows.py mempalace_watcher\\__main__.py tests\\test_watcher.py` passed.
- `python -m unittest discover -s tests -v` passed with 24 tests.
- `.venv\\Scripts\\python.exe -m unittest discover -s tests -v` passed with 32 tests.
- Live API smoke check against the current dashboard showed `/api/actions/refresh-all` returning in about 58 ms and starting all 6 tracked refresh-capable projects.
- Live API smoke check against the current dashboard on `127.0.0.1:50874` showed `/api/project` returning full `log_lines` and `log_text` for a tracked project.
- A previously stale tracked project was re-baselined in the watcher DB and then scanned as `fresh` with `change_count=0` and `critical_change_count=0`.
- Served dashboard HTML on `127.0.0.1:50874` includes `Project log` in the inspector and no longer includes `Copy log` in the per-row menu.
- `cmd /c start_dashboard.cmd` starts the desktop dashboard without a visible console and returns immediately.
- `cmd /c start_dashboard.cmd` still returns immediately after the bootstrap change.
- Live API smoke check against `127.0.0.1:8787` showed 6 tracked projects, row-level project menus, parallel refresh launch, and a post-refresh scan with 6 `fresh` / 0 `needs refresh`.
- Served dashboard HTML script passed `node --check` after fixing embedded `\\n` handling in `web.py`.
- Served dashboard HTML script passed `node --check` after adding refresh toolbar actions.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after adding visible refresh status feedback.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after switching refresh launch to resolved PowerShell binaries.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after adding live per-project refresh progress state.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after enabling streamed refresh progress updates from stdout.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after switching refresh starts to parallel launch and removing live stdout text from the UI.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after moving `Copy log` out of project rows and into a collapsible project-log drawer with clipboard fallback.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after removing duplicate `Refresh selected` controls from the inspector and moving toolbar actions to their proper panels.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after adding optimistic per-project refresh feedback and row highlighting.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after adding row-menu refresh status badges and faster polling.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after adding per-project refresh duration prediction chips.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after relabeling `change_count` to `Pending` and restoring the real pending diff after refresh.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after replacing the compact pending counter with explicit `changed files` and `critical changes` wording.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after fixing pending-change cell wrapping with a dedicated no-break layout.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after redesigning the dashboard summary and project actions with a more technical dark UI.
- Served dashboard HTML script passed `python -m py_compile` and unit tests after adding a collapsible project log drawer, canonical log text, and clipboard fallback for WebView2.
- Served dashboard HTML script was rechecked after fixing an unescaped `\n` in `copyProjectLog`, and the live `127.0.0.1:8787` response is now script-valid again.
- Served dashboard HTML script passed after adding background scan-state rendering and the animated scan banner.
- `python -m py_compile ...` passed after simplifying the scan banner and fixing the successful-refresh scan baseline regression.
- `pywebview` was installed into the project-local `.venv` for WebView2 desktop mode.
- Local HTTP smoke check passed against a temporary fixture project: `/api/summary` and `/api/projects` returned expected data.

## Open Loops
- None.
