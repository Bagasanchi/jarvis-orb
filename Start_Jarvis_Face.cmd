@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_jarvis_face.py
) else (
    python run_jarvis_face.py
)
if errorlevel 1 pause
