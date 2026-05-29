@echo off
REM Double-click to start TBCC tray supervisor (no terminal commands needed).
cd /d "%~dp0"
powershell.exe -NoProfile -Sta -ExecutionPolicy Bypass -File "%~dp0tbcc-supervisor.ps1"
exit /b %ERRORLEVEL%
