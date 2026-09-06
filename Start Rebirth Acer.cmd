@echo off
setlocal
cd /d "%~dp0"
set "KIDZ_TEST_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "KIDZ_TEST_PYTHON=%~dp0.venv\Scripts\python.exe"
if defined KIDZDISCO_PYTHON set "KIDZ_TEST_PYTHON=%KIDZDISCO_PYTHON%"
"%KIDZ_TEST_PYTHON%" scripts\start_kids_test.py --audience %*
set "KIDZ_TEST_RESULT=%ERRORLEVEL%"
if not "%KIDZ_TEST_RESULT%"=="0" pause
exit /b %KIDZ_TEST_RESULT%
