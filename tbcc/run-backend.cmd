@echo off
REM Double-click or run from Explorer: always starts Uvicorn from THIS folder's backend (avoids wrong cwd).
title TBCC-Backend
cd /d "%~dp0backend"
echo Running from: %CD%
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-exclude scripts --reload-delay 1
if errorlevel 1 pause
