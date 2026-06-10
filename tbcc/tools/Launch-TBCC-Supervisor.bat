@echo off
REM TBCC tray supervisor - single hidden host (no flashing console).
cd /d "%~dp0"
set TBCC_SUPERVISOR_TRAY=1
powershell.exe -NoProfile -Sta -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0tbcc-supervisor.ps1"
if errorlevel 1 (
  echo TBCC Supervisor failed to start. Check tbcc\.tbcc-run\supervisor.log
  pause
)
exit /b %ERRORLEVEL%
