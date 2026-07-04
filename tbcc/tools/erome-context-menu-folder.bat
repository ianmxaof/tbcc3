@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0erome-context-menu.ps1" -Mode folder -PathArgs "%~1"
exit /b %ERRORLEVEL%
