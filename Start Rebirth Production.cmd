@echo off
setlocal
cd /d "%~dp0"
set "REBIRTH_LAUNCH_PYTHON=%USERPROFILE%\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe"
if not exist "%REBIRTH_LAUNCH_PYTHON%" (
  echo Verified Python environment was not found. No environment was changed.
  pause
  exit /b 1
)
"%REBIRTH_LAUNCH_PYTHON%" "%~dp0scripts\launch_production.py" %*
if errorlevel 1 pause
