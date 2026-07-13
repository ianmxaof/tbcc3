@echo off
REM Fallback launcher (prefer .vbs from context menu - no window flash).
REM Kept for manual/debug runs.
setlocal
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Sta -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0..\scripts\tbcc-capture-secret.ps1" -FromClipboard -Quiet
exit /b %ERRORLEVEL%
