@echo off
setlocal
cd /d "%~dp0"
set "MAC_CHECK_PYTHON=python"
if defined KIDZDISCO_PYTHON set "MAC_CHECK_PYTHON=%KIDZDISCO_PYTHON%"
"%MAC_CHECK_PYTHON%" -X utf8 "%~dp0scripts\check_mac_connection.py" %*
exit /b %ERRORLEVEL%
