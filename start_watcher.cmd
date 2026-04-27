@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    python -m venv .venv
)

if not exist ".venv\Scripts\pythonw.exe" (
    echo Missing .venv\Scripts\pythonw.exe
    exit /b 1
)

set "PYTHONW_EXE=%CD%\.venv\Scripts\pythonw.exe"
wscript.exe //nologo "%~dp0start_watcher.vbs" "%PYTHONW_EXE%"

endlocal
