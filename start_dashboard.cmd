@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    python -m venv .venv
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
set "PYTHONW_EXE=%CD%\.venv\Scripts\pythonw.exe"
%PYTHON_EXE% -c "import webview" >nul 2>nul
if errorlevel 1 (
    %PYTHON_EXE% -m pip install -r "%~dp0requirements.txt"
)
wscript.exe //nologo "%~dp0start_dashboard.vbs" "%PYTHONW_EXE%"

endlocal
