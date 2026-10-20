@echo off
setlocal
cd /d "%~dp0"
set "MATAHARI_CHECK_PYTHON=%USERPROFILE%\.gemini\antigravity\scratch\harukaze2026_kidzdisco_windows\.venv\Scripts\python.exe"
if not exist "%MATAHARI_CHECK_PYTHON%" (
  echo Verified Python environment is missing. No environment was changed.
  pause
  exit /b 1
)
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
"%MATAHARI_CHECK_PYTHON%" -B "%~dp0tools\matahari_face_mesh_check.py" %*
if errorlevel 1 pause
