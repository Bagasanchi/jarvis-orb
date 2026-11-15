@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m jarvis.setup --gui
exit /b %errorlevel%
:failed
echo Setup failed. Install Python 3.12 or newer with tkinter and PATH enabled, then try again.
pause
exit /b 1
