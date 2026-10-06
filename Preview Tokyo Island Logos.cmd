@echo off
setlocal
cd /d "%~dp0"
set "TOKYO_PREVIEW_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%TOKYO_PREVIEW_PYTHON%" (
  echo Verified Python 3.12 was not found. Nothing was installed.
  pause
  exit /b 1
)
"%TOKYO_PREVIEW_PYTHON%" -I -S -B "%~dp0scripts\preview_transition_logos.py" %*
if errorlevel 1 pause
