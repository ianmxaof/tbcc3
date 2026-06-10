@echo off
REM Debug: visible console stays open; tray icon should appear in notification area.
cd /d "%~dp0"
set TBCC_SUPERVISOR_TRAY=1
powershell.exe -NoProfile -Sta -NoExit -ExecutionPolicy Bypass -File "%~dp0tbcc-supervisor.ps1" -ShowConsole
