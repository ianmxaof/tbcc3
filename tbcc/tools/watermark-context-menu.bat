@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0watermark-context-menu.ps1" -Mode file -PathArgs "%~1"
exit /b %ERRORLEVEL%
