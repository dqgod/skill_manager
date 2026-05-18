@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Run: python -m venv .venv
    pause
    exit /b 1
)

REM Clear previous logs
if exist "%USERPROFILE%\.skill-manager\logs\app.log" del /q "%USERPROFILE%\.skill-manager\logs\app.log"
if exist "%USERPROFILE%\.skill-manager\logs\crash.log" del /q "%USERPROFILE%\.skill-manager\logs\crash.log"

call ".venv\Scripts\python.exe" -m src.main
pause
