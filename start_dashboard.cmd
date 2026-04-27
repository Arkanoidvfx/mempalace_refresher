@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    python -m venv .venv
)

set "PYTHONW_EXE=%CD%\.venv\Scripts\pythonw.exe"
wscript.exe //nologo "%~dp0start_dashboard.vbs" "%PYTHONW_EXE%"

endlocal
