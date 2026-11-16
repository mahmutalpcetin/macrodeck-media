@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo First create the virtual environment and install desktop\requirements.txt.
    echo See README.md for setup instructions.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "desktop\app.py" %*
